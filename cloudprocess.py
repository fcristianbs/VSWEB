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
from models import FilaProcessamento, Projeto, Documento, SecaoProjeto, ConfiguracaoSistema
import processador
from automacao import MotorGPM

# ==========================================
# CONFIGURAÇÕES DO ROBÔ (Preencha aqui)
# ==========================================
GPM_USUARIO = os.getenv("GPM_USUARIO")
GPM_SENHA = os.getenv("GPM_SENHA")
TEMPO_ESPERA_FILA = 15  # Segundos que ele espera antes de checar a fila de novo
TEMPO_PAUSA_ENTRE_OBRAS = 30 # Respiro obrigatório para o GPM não bloquear seu IP

def log_robo(msg):
    """Imprime os logs no terminal do Worker e força a exibição (flush=True)"""
    agora = datetime.now().strftime("%H:%M:%S")
    try:
        print(f"[{agora}] 🤖 {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"[{agora}] [ROBO] {msg}".encode('ascii', 'ignore').decode('ascii'), flush=True)

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
                id_temp = str(uuid4())
                nome_orig = f"{id_temp}_orig.jpg"
                caminho_orig = os.path.join(pasta_extracao, nome_orig)
                
                with z.open(file_info) as source, open(caminho_orig, "wb") as target:
                    shutil.copyfileobj(source, target)
                
                arquivos_extraidos.append({'id': id_temp, 'caminho': caminho_orig, 'nome_arquivo': nome_orig})
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
    
    try:
        motor.baixar_obra_api(codigo)
    except ValueError as e:
        if "SESSAO_EXPIRADA" in str(e): raise Exception("SESSAO_EXPIRADA")
        raise ValueError(f"Falha na extração GPM: {str(e)}")

    atualiza_msg("📂 Procurando o arquivo ZIP no sistema...")
    arquivos_zip = [f for f in os.listdir(DOWNLOADS_GPM) if f.endswith('.zip') and codigo in f]
    if not arquivos_zip:
        arquivos_zip = [f for f in os.listdir(DOWNLOADS_GPM) if f.endswith('.zip')]
        if not arquivos_zip: raise ValueError("ZIP não encontrado.")
            
    arquivos_zip.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOADS_GPM, x)), reverse=True)
    caminho_zip_master = os.path.join(DOWNLOADS_GPM, arquivos_zip[0])

    atualiza_msg("📦 Extraindo imagens do pacote ZIP...")
    imagens_para_processar, pasta_temp = extrair_arquivos_zip(caminho_zip_master, codigo)
    if not imagens_para_processar: raise ValueError("O arquivo ZIP estava vazio ou sem imagens.")

    projeto = Projeto.query.filter_by(codigo_obra=codigo).first()
    if not projeto:
        projeto = Projeto(codigo_obra=codigo, nome_obra=tarefa.nome_obra, status_global='PENDENTE')
        db.session.add(projeto)
        db.session.flush()

    Documento.query.filter_by(projeto_id=projeto.id).delete()

    ordem_global = 9000
    for idx, img in enumerate(imagens_para_processar):
        atualiza_msg(f"🧠 Processando IA: {idx + 1}/{len(imagens_para_processar)} imagens...")
        
        is_doc, caminho_proc, tipo_doc = processador.recortar_caderno_preciso(img['caminho'])
        nome_proc = os.path.basename(caminho_proc)
        
        novo_nome_orig = f"{projeto.id}_ORIG_{img['nome_arquivo']}"
        novo_nome_proc = f"{projeto.id}_PROC_{nome_proc}"
        
        shutil.copy(img['caminho'], os.path.join(DRIVE_FOLDER, novo_nome_orig))
        shutil.copy(caminho_proc, os.path.join(DRIVE_FOLDER, novo_nome_proc))
        
        novo_doc = Documento(
            id=img['id'], projeto_id=projeto.id, 
            caminho_original=novo_nome_orig, caminho_cortado=novo_nome_proc, 
            categoria=tipo_doc, ordem_pagina=ordem_global, is_upload_manual=False
        )
        db.session.add(novo_doc)
        ordem_global += 1

    atualiza_msg("💾 Gravando dados finais no Drive...")
    db.session.commit()
    try:
        os.remove(caminho_zip_master)
        shutil.rmtree(pasta_temp)
    except: pass

    motor.callback = log_robo
    log_robo(f"✅ Obra {codigo} finalizada com sucesso!")

def iniciar_worker():
    log_robo("☁️ CloudProcess Iniciado! Preparando ignição...")
    
    motor = MotorGPM(GPM_USUARIO, GPM_SENHA, "", DOWNLOADS_GPM, log_robo)
    if not motor.autenticar():
        log_robo("❌ Erro fatal: Não foi possível fazer o login inicial no GPM.")
        return

    log_robo("✅ Motor autenticado. Fique de olho neste terminal para ver o processamento!")
    
    with app.app_context():
        while True:
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
                else:
                    tarefa.status_fila = 'ERRO'
                    tarefa.log_erro = erro_msg
                    log_robo(f"❌ Falha na Obra {tarefa.codigo_obra}: {erro_msg}")
                    
                tarefa.data_processamento = datetime.now()
                db.session.commit()
                time.sleep(TEMPO_ESPERA_FILA)

if __name__ == "__main__":
    if GPM_USUARIO == "SEU_USUARIO_AQUI":
        print("⚠️ ALERTA: Preencha seu usuário e senha do GPM no topo do arquivo cloudprocess.py!")
    else:
        iniciar_worker()