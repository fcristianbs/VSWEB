import sys
import os
from dotenv import load_dotenv

load_dotenv()
import time
import shutil
import zipfile
from uuid import uuid4
from datetime import datetime

# Importamos o contexto do Flask e do Banco de Dados
from app import app, db, UPLOAD_FOLDER, DOWNLOADS_GPM, DRIVE_FOLDER
from models import FilaProcessamento, Projeto, Documento, SecaoProjeto, ConfiguracaoSistema, LogSistema
import processador
from automacao import MotorGPM
from datetime import datetime, timedelta
import requests
import re

# ==========================================
# CONFIGURAÇÕES DO ROBÔ (Preencha aqui)
# ==========================================
GPM_USUARIO = os.getenv("GPM_USUARIO")
GPM_SENHA = os.getenv("GPM_SENHA")
TEMPO_ESPERA_FILA = 15  # Segundos que ele espera antes de checar a fila de novo
TEMPO_PAUSA_ENTRE_OBRAS = 30 # Respiro obrigatório para o GPM não bloquear seu IP

def log_robo(msg, nivel='INFO'):
    """Imprime os logs no terminal e salva no Banco de Dados para o Painel Admin"""
    agora = datetime.now()
    msg_str = str(msg)
    
    # 1. Print no Terminal
    try:
        print(f"[{agora.strftime('%H:%M:%S')}] 🤖 {msg_str}", flush=True)
    except:
        pass

    # 2. Salva no Banco de Dados (com retry para SQLite)
    # Otimização: Não salvamos logs repetitivos de progresso de IA no banco para evitar lock
    if "Processando IA" in msg_str and nivel == 'INFO':
        return 

    for tentativa in range(5):
        try:
            with app.app_context():
                novo_log = LogSistema(mensagem=msg_str, nivel=nivel, data_evento=agora)
                db.session.add(novo_log)
                db.session.commit()
                break # Sucesso
        except Exception as e:
            if "locked" in str(e).lower() and tentativa < 4:
                time.sleep(1) # Espera 1s e tenta de novo
                continue
            print(f"❌ Erro ao salvar log no banco: {e}")
            break

def verificar_se_pausado():
    """Consulta o banco de dados para ver se você apertou o botão de Pausa no painel"""
    with app.app_context():
        config = ConfiguracaoSistema.query.filter_by(chave='status_robo').first()
        if config and config.valor == 'PAUSADO':
            return True
    return False

def extrair_arquivos_zip(caminho_zip, codigo_obra):
    pasta_extracao = os.path.join(DOWNLOADS_GPM, f"extracao_{codigo_obra}")
    if not os.path.exists(pasta_extracao):
        os.makedirs(pasta_extracao)
        
    arquivos_extraidos = []
    with zipfile.ZipFile(caminho_zip, 'r') as z:
        for file_info in z.infolist():
            if not file_info.is_dir() and file_info.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                # Determinístico: Nome do arquivo original sanitizado
                nome_limpo = re.sub(r'[^a-zA-Z0-9.]', '_', file_info.filename)
                caminho_orig = os.path.join(pasta_extracao, f"orig_{nome_limpo}")
                
                # Só extrai se não existir (ajuda na retomada)
                if not os.path.exists(caminho_orig):
                    with z.open(file_info) as source, open(caminho_orig, "wb") as target:
                        shutil.copyfileobj(source, target)
                
                arquivos_extraidos.append({
                    'id': nome_limpo, 
                    'caminho': caminho_orig, 
                    'nome_arquivo': file_info.filename
                })
    return arquivos_extraidos, pasta_extracao

def processar_obra(tarefa, motor):
    """A engrenagem principal que cuida de uma obra"""
    codigo = tarefa.codigo_obra
    
    # Transmissor Ao Vivo para a Tela do HTML
    def atualiza_msg(msg):
        log_robo(msg) # Mostra no terminal preto instantaneamente
        tarefa.log_erro = msg # Salva no banco pro navegador ler
        db.session.commit()

    motor.callback = atualiza_msg

    atualiza_msg(f"🚀 Iniciando obra #{codigo} - {tarefa.nome_obra}")
    
    # 1. ETAPA: DOWNLOAD
    tarefa.etapa = 'BAIXANDO'
    db.session.commit()
    
    # Verifica se já temos um ZIP recente para evitar baixar de novo se caiu no meio
    arquivos_zip = [f for f in os.listdir(DOWNLOADS_GPM) if f.endswith('.zip') and codigo in f]
    if not arquivos_zip:
        try:
            motor.baixar_obra_api(codigo)
            arquivos_zip = [f for f in os.listdir(DOWNLOADS_GPM) if f.endswith('.zip') and codigo in f]
        except ValueError as e:
            if "SESSAO_EXPIRADA" in str(e): raise Exception("SESSAO_EXPIRADA")
            raise ValueError(f"Falha na extração GPM: {str(e)}")

    if not arquivos_zip: raise ValueError("ZIP não encontrado após download.")
    arquivos_zip.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOADS_GPM, x)), reverse=True)
    caminho_zip_master = os.path.join(DOWNLOADS_GPM, arquivos_zip[0])

    # 2. ETAPA: EXTRAÇÃO
    tarefa.etapa = 'EXTRAINDO'
    db.session.commit()
    
    atualiza_msg("📦 Extraindo imagens do pacote ZIP...")
    imagens_para_processar, pasta_temp = extrair_arquivos_zip(caminho_zip_master, codigo)
    if not imagens_para_processar: raise ValueError("O arquivo ZIP estava vazio ou sem imagens.")

    projeto = Projeto.query.filter_by(codigo_obra=codigo).first()
    if not projeto:
        projeto = Projeto(
            codigo_obra=codigo, nome_obra=tarefa.nome_obra, 
            status_global='PENDENTE', data_limite=tarefa.data_limite_runrunit,
            data_obra=tarefa.data_obra
        )
        db.session.add(projeto)
        db.session.flush()

    # 3. ETAPA: PROCESSAMENTO IA
    tarefa.etapa = 'PROCESSANDO_IA'
    db.session.commit()

    # Busca o que já foi processado para esta obra (Checkpoints)
    docs_existentes = {d.id for d in Documento.query.filter_by(projeto_id=projeto.id).all()}
    
    ordem_global = 9000
    total_imgs = len(imagens_para_processar)
    
    for idx, img in enumerate(imagens_para_processar):
        if img['id'] in docs_existentes:
            log_robo(f"⏭️ Pulando imagem {idx+1}/{total_imgs} (Já processada)")
            continue

        tarefa.dados_checkpoint = f"{idx + 1}/{total_imgs}"
        atualiza_msg(f"🧠 Processando IA: {idx + 1}/{total_imgs} imagens...")
        
        is_doc, caminho_proc, tipo_doc = processador.recortar_caderno_preciso(img['caminho'])
        nome_proc = os.path.basename(caminho_proc)
        
        # Nomes fixos baseados no ID determinístico para evitar duplicatas físicas
        nome_arquivo_limpo = os.path.basename(img['nome_arquivo'])
        novo_nome_orig = f"{projeto.id}_ORIG_{img['id']}_{nome_arquivo_limpo}"
        novo_nome_proc = f"{projeto.id}_PROC_{img['id']}_{nome_proc}"
        
        if not os.path.exists(os.path.join(DRIVE_FOLDER, novo_nome_orig)):
            shutil.copy(img['caminho'], os.path.join(DRIVE_FOLDER, novo_nome_orig))
        if not os.path.exists(os.path.join(DRIVE_FOLDER, novo_nome_proc)):
            shutil.copy(caminho_proc, os.path.join(DRIVE_FOLDER, novo_nome_proc))
        
        novo_doc = Documento(
            id=img['id'], projeto_id=projeto.id, 
            caminho_original=novo_nome_orig, caminho_cortado=novo_nome_proc, 
            categoria=tipo_doc, ordem_pagina=ordem_global + idx, is_upload_manual=False
        )
        db.session.add(novo_doc)
        db.session.commit() # Commitamos a cada imagem para garantir o checkpoint real

    atualiza_msg("💾 Gravando dados finais no Drive...")
    db.session.commit()
    try:
        os.remove(caminho_zip_master)
        shutil.rmtree(pasta_temp)
    except: pass

    motor.callback = log_robo
    log_robo(f"✅ Obra {codigo} finalizada com sucesso!", nivel='SUCESSO')

def mineracao_diaria():
    """Busca obras dos últimos 3 meses no Runrun.it e enfileira"""
    log_robo("🔎 Iniciando mineração automática de obras (Últimos 3 meses)...")
    
    RUNRUNIT_APP_KEY = os.getenv("RUNRUNIT_APP_KEY")
    RUNRUNIT_USER_TOKEN = os.getenv("RUNRUNIT_USER_TOKEN")
    
    if not RUNRUNIT_APP_KEY or not RUNRUNIT_USER_TOKEN:
        log_robo("⚠️ Runrun.it API Keys não configuradas. Pulando mineração.", nivel='WARNING')
        return

    headers = { "App-Key": RUNRUNIT_APP_KEY, "User-Token": RUNRUNIT_USER_TOKEN }
    params = { "is_closed": "false", "limit": 1000 }
    
    try:
        response = requests.get("https://runrun.it/api/v1.0/tasks", headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            log_robo(f"❌ Erro na API do Runrun.it: {response.status_code}", nivel='ERROR')
            return
            
        tarefas = response.json()
        data_corte = datetime.now() - timedelta(days=90)
        adicionadas = 0
        
        for tarefa in tarefas:
            data_string = tarefa.get("updated_at", tarefa.get("created_at", ""))
            try:
                data_obj = datetime.strptime(data_string[:10], "%Y-%m-%d")
            except:
                data_obj = datetime.now()
                
            if data_obj >= data_corte.replace(hour=0, minute=0, second=0, microsecond=0):
                titulo = tarefa.get("title", "")
                match = re.search(r'\b(\d{6,})\b', titulo)
                
                if match:
                    codigo = match.group(1)
                    # Verifica se já existe
                    existe = FilaProcessamento.query.filter_by(codigo_obra=codigo).first()
                    ja_feito = Projeto.query.filter_by(codigo_obra=codigo).first()
                    
                    if not existe and not ja_feito:
                        nova_tarefa = FilaProcessamento(
                            codigo_obra=codigo,
                            nome_obra=titulo,
                            data_obra=data_obj.date(),
                            status_fila='AGUARDANDO'
                        )
                        db.session.add(nova_tarefa)
                        adicionadas += 1
                        
                        # Commits em lote (50 em 50) para não travar o SQLite por muito tempo
                        if adicionadas % 50 == 0:
                            db.session.commit()
        
        db.session.commit()
        if adicionadas > 0:
            log_robo(f"✨ Mineração concluída: {adicionadas} novas obras enfileiradas.", nivel='SUCESSO')
        else:
            log_robo("🛌 Mineração concluída: Nenhuma obra nova encontrada.")
            
    except Exception as e:
        log_robo(f"❌ Erro durante a mineração: {e}", nivel='ERROR')

def limpeza_obras_antigas():
    """Remove obras com mais de 3 meses do banco e do HD"""
    log_robo("🧹 Iniciando limpeza de obras antigas (> 90 dias)...")
    data_limite = (datetime.now() - timedelta(days=90)).date()
    
    try:
        # Busca projetos antigos
        projetos_antigos = Projeto.query.filter(Projeto.data_obra < data_limite).all()
        removidos = 0
        
        for proj in projetos_antigos:
            # Remove arquivos físicos
            for doc in proj.documentos:
                try:
                    caminho_orig = os.path.join(DRIVE_FOLDER, doc.caminho_original)
                    caminho_proc = os.path.join(DRIVE_FOLDER, doc.caminho_cortado)
                    if os.path.exists(caminho_orig): os.remove(caminho_orig)
                    if os.path.exists(caminho_proc): os.remove(caminho_proc)
                except: pass
            
            db.session.delete(proj)
            removidos += 1
            
        db.session.commit()
        if removidos > 0:
            log_robo(f"♻️ Limpeza concluída: {removidos} projetos antigos removidos.", nivel='INFO')
        else:
            log_robo("✅ Limpeza concluída: Nada para remover.")
            
    except Exception as e:
        log_robo(f"❌ Erro durante a limpeza: {e}", nivel='ERROR')

def iniciar_worker():
    log_robo("☁️ CloudProcess Iniciado! Preparando ignição...")
    
    with app.app_context():
        # Limpa os "fantasmas" para que possam ser retomados (Checkpoints)
        tarefas_fantasmas = FilaProcessamento.query.filter_by(status_fila='PROCESSANDO').all()
        for t in tarefas_fantasmas:
            t.status_fila = 'AGUARDANDO'
            log_robo(f"🔄 Obra #{t.codigo_obra} marcada para retomada.")
        db.session.commit()
    
    motor = MotorGPM(GPM_USUARIO, GPM_SENHA, "", DOWNLOADS_GPM, log_robo)
    if not motor.autenticar():
        log_robo("❌ Erro fatal: Não foi possível fazer o login inicial no GPM.")
        return

    log_robo("✅ Motor autenticado. Fique de olho no Painel Admin para acompanhar!")
    
    # Marcadores de tempo para rotinas automáticas
    ultima_mineracao = datetime.now() - timedelta(hours=2) # Força rodar logo que liga
    ultima_limpeza = datetime.now() - timedelta(days=1)
    
    with app.app_context():
        while True:
            agora = datetime.now()
            
            # 1. Rotina de Mineração (A cada 1 hora ou se solicitado via Painel)
            forca_minera = ConfiguracaoSistema.query.filter_by(chave='forcar_mineracao').first()
            if (agora - ultima_mineracao).total_seconds() > 3600 or (forca_minera and forca_minera.valor == 'SIM'):
                mineracao_diaria()
                ultima_mineracao = agora
                if forca_minera:
                    forca_minera.valor = 'NAO'
                    db.session.commit()
                
            # 2. Rotina de Limpeza (A cada 24 horas)
            if (agora - ultima_limpeza).total_seconds() > 86400:
                limpeza_obras_antigas()
                ultima_limpeza = agora

            if verificar_se_pausado():
                log_robo("⏸️ Robô pausado via painel. Aguardando...")
                time.sleep(TEMPO_ESPERA_FILA)
                continue

            tarefa = FilaProcessamento.query.filter_by(status_fila='AGUARDANDO').order_by(FilaProcessamento.data_adicao.asc()).first()

            if not tarefa:
                # O batimento cardíaco do robô para você saber que ele não travou:
                log_robo("Aguardando novas obras na fila...")
                time.sleep(TEMPO_ESPERA_FILA)
                continue

            tarefa.status_fila = 'PROCESSANDO'
            db.session.commit()

            try:
                processar_obra(tarefa, motor)
                
                tarefa.status_fila = 'SUCESSO'
                tarefa.data_processamento = datetime.now()
                db.session.commit()
                
                log_robo(f"Respirando por {TEMPO_PAUSA_ENTRE_OBRAS} segundos antes da próxima...")
                time.sleep(TEMPO_PAUSA_ENTRE_OBRAS)

            except Exception as e:
                db.session.rollback()
                erro_msg = str(e)
                
                if "SESSAO_EXPIRADA" in erro_msg:
                    log_robo("⚠️ Sessão do GPM expirou. Refazendo login...")
                    motor.autenticar()
                    tarefa.status_fila = 'AGUARDANDO'
                    db.session.commit()
                else:
                    # Primeiro salvamos o erro na tarefa
                    tarefa.status_fila = 'ERRO'
                    tarefa.log_erro = erro_msg
                    tarefa.data_processamento = datetime.now()
                    db.session.commit()
                    
                    # Só depois geramos o log (que também tenta commitar no LogSistema)
                    log_robo(f"❌ Falha na Obra {tarefa.codigo_obra}: {erro_msg}", nivel='ERROR')
                
                time.sleep(TEMPO_ESPERA_FILA)

if __name__ == "__main__":
    if GPM_USUARIO == "SEU_USUARIO_AQUI":
        print("⚠️ ALERTA: Preencha seu usuário e senha do GPM no topo do arquivo cloudprocess.py!")
    else:
        iniciar_worker()