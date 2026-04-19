import os, cv2, zipfile, numpy as np, threading, shutil
import requests, re
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, send_from_directory, Response, current_app
from uuid import uuid4
from PIL import Image
import processador 
from automacao import MotorGPM
from models import db, Projeto, SecaoProjeto, Documento, FilaProcessamento, ConfiguracaoSistema 
from extensions import db_imagens, pdfs_gerados, log_queue

api_bp = Blueprint('api', __name__)

RUNRUNIT_APP_KEY = os.getenv("RUNRUNIT_APP_KEY")
RUNRUNIT_USER_TOKEN = os.getenv("RUNRUNIT_USER_TOKEN")

def aplicar_rotacao_cv2(img, angulo):
    """Aplica a rotação física real no array da imagem."""
    angulo = int(angulo) % 360
    if angulo == 90 or angulo == -270: return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif angulo == 180 or angulo == -180: return cv2.rotate(img, cv2.ROTATE_180)
    elif angulo == 270 or angulo == -90: return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img

def extrair_zip_apenas(caminho_zip):
    resultados = []
    with zipfile.ZipFile(caminho_zip, 'r') as z:
        for file_info in z.infolist():
            if not file_info.is_dir() and file_info.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                id_temp = str(uuid4())
                nome_orig = f"{id_temp}_orig.jpg"
                caminho_orig = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_orig)
                
                with z.open(file_info) as source, open(caminho_orig, "wb") as target:
                    shutil.copyfileobj(source, target)
                
                db_imagens[id_temp] = {'original': nome_orig, 'processada': nome_orig, 'is_manual': False}
                resultados.append({'id': id_temp})
    return resultados

# --- ROTAS ---

@api_bp.route('/api/carregar_projeto/<projeto_id>')
def carregar_projeto(projeto_id):
    try:
        projeto = Projeto.query.get(projeto_id)
        if not projeto: return jsonify({'sucesso': False, 'erro': 'Projeto não encontrado'}), 404
        
        # 1. Carrega as Seções (Gavetas)
        secoes_json = []
        for sec in projeto.secoes:
            secoes_json.append({
                'nome_secao': sec.nome_secao,
                'status_secao': sec.status_secao,
                'observacao': sec.observacao
            })
            
        # 2. Carrega os Documentos
        docs_json = []
        for doc in projeto.documentos:
            orig = doc.caminho_original or ""
            proc = doc.caminho_cortado or orig
            is_manual = getattr(doc, 'is_upload_manual', False)
            
            db_imagens[doc.id] = {'original': orig, 'processada': proc, 'is_manual': is_manual}
            
            if orig:
                orig_drive = os.path.join(current_app.config['DRIVE_FOLDER'], orig)
                orig_up = os.path.join(current_app.config['UPLOAD_FOLDER'], orig)
                if os.path.exists(orig_drive) and not os.path.exists(orig_up): shutil.copy(orig_drive, orig_up)
            
            if proc:
                proc_drive = os.path.join(current_app.config['DRIVE_FOLDER'], proc)
                proc_up = os.path.join(current_app.config['UPLOAD_FOLDER'], proc)
                if os.path.exists(proc_drive) and not os.path.exists(proc_up): shutil.copy(proc_drive, proc_up)
            
            docs_json.append({
                'id': doc.id,
                'url': f"/uploads/{proc}",
                'url_orig': f"/uploads/{orig}",
                'tipo': doc.categoria,
                'ordem': doc.ordem_pagina,
                'is_doc': doc.categoria != 'FOTOS',
                'is_manual': is_manual
            })
            
        return jsonify({
            'sucesso': True, 
            'projeto': { 
                'codigo_obra': projeto.codigo_obra, 
                'nome_obra': getattr(projeto, 'nome_obra', ''), 
                'status_manual': projeto.status_global 
            }, 
            'secoes': secoes_json,
            'documentos': docs_json
        })
    except Exception as e:
        return jsonify({'sucesso': False, 'erro': str(e)}), 500

@api_bp.route('/api/runrunit/obras_recentes')
def api_obras_recentes():
    """Rota que o painel do Drive vai chamar para listar as obras"""
    headers = {
        "App-Key": RUNRUNIT_APP_KEY,
        "User-Token": RUNRUNIT_USER_TOKEN
    }
    params = { "is_closed": "false", "limit": 1000 }
    
    try:
        response = requests.get("https://runrun.it/api/v1.0/tasks", headers=headers, params=params)
        
        if response.status_code != 200:
            return jsonify({"sucesso": False, "erro": f"Falha na API: {response.status_code}"}), 500
            
        tarefas = response.json()
        codigos_extraidos = []
        
        # Lê a data que veio do HTML. Se não vier nada, usa 15 dias como padrão de segurança.
        data_param = request.args.get('data')
        if data_param:
            data_corte = datetime.strptime(data_param, "%Y-%m-%d")
        else:
            data_corte = datetime.now() - timedelta(days=15)
        
        for tarefa in tarefas:
            data_string = tarefa.get("updated_at", tarefa.get("created_at", ""))
            try:
                data_obj = datetime.strptime(data_string[:10], "%Y-%m-%d")
            except:
                data_obj = datetime.now()
                
            if data_obj >= data_corte:
                titulo = tarefa.get("title", "")
                match = re.search(r'\b(\d{6,})\b', titulo)
                
                if match:
                    codigos_extraidos.append({
                        "codigo": match.group(1),
                        "data_formatada": data_obj.strftime("%d/%m/%Y"),
                        "data_iso": data_obj.strftime("%Y-%m-%d"),
                        "titulo_completo": titulo,
                        "id_tarefa": tarefa.get("id")
                    })
                    
        return jsonify({"sucesso": True, "obras": codigos_extraidos})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500
    
@api_bp.route('/buscar_gpm', methods=['POST'])
def buscar_gpm():
    dados = request.json
    def notify(msg): log_queue.put(msg)
    motor = MotorGPM(dados['user'], dados['pass'], dados['codigo'], current_app.config['DOWNLOADS_GPM'], notify)
    threading.Thread(target=motor.rodar).start()
    return jsonify({'status': 'ok'})

@api_bp.route('/progresso_gpm')
def progresso_gpm():
    def generate():
        while True:
            msg = log_queue.get()
            yield f"data: {msg}\\n\\n"
            if "✅" in msg or "❌" in msg: break
    return Response(generate(), mimetype='text/event-stream')

@api_bp.route('/processar_download_gpm', methods=['POST'])
def processar_download_gpm():
    try:
        arquivos = [f for f in os.listdir(current_app.config['DOWNLOADS_GPM']) if f.endswith('.zip')]
        if not arquivos: return jsonify({'erro': 'ZIP não encontrado'}), 400
        arquivos.sort(key=lambda x: os.path.getmtime(os.path.join(current_app.config['DOWNLOADS_GPM'], x)), reverse=True)
        return jsonify(extrair_zip_apenas(os.path.join(current_app.config['DOWNLOADS_GPM'], arquivos[0])))
    except Exception as e: return jsonify({'erro': str(e)}), 500

@api_bp.route('/upload', methods=['POST'])
def upload():
    files = request.files.getlist('fotos')
    res = []
    for f in files:
        id_img = str(uuid4())
        nome_orig = f"{id_img}_orig.jpg"
        path_orig = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_orig)
        f.save(path_orig)
        db_imagens[id_img] = {'original': nome_orig, 'processada': nome_orig, 'is_manual': False}
        res.append({'id': id_img}) 
    return jsonify(res)

# --- NOVA ROTA: UPLOAD MANUAL (Bypass IA) ---
@api_bp.route('/upload_manual', methods=['POST'])
def upload_manual():
    files = request.files.getlist('fotos')
    tipo_doc = request.form.get('tipo_documento', 'DOCUMENTO')
    res = []
    
    for f in files:
        id_img = str(uuid4())
        nome_orig = f"{id_img}_orig.jpg"
        path_orig = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_orig)
        f.save(path_orig)
        
        # A magia está aqui: is_manual = True e ele usa o original como processado
        db_imagens[id_img] = {'original': nome_orig, 'processada': nome_orig, 'is_manual': True}
        
        res.append({
            'id': id_img,
            'url': f"/uploads/{nome_orig}",
            'url_orig': f"/uploads/{nome_orig}",
            'is_doc': tipo_doc != 'FOTOS',
            'tipo': tipo_doc,
            'is_manual': True
        })
    return jsonify(res)

@api_bp.route('/processar_imagem_unica', methods=['POST'])
def processar_imagem_unica():
    dados = request.json
    id_img = dados['id']
    nome_orig = db_imagens[id_img]['original']
    caminho_orig = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_orig)
    
    is_doc, caminho_proc, tipo_doc = processador.recortar_caderno_preciso(caminho_orig)
    nome_proc = os.path.basename(caminho_proc)
    
    db_imagens[id_img]['processada'] = nome_proc
    return jsonify({
        'id': id_img, 
        'url': f"/uploads/{nome_proc}", 
        'url_orig': f"/uploads/{nome_orig}",
        'is_doc': is_doc, 
        'tipo': tipo_doc,
        'is_manual': False
    })

@api_bp.route('/rotacionar_apenas', methods=['POST'])
def rotacionar_apenas():
    dados = request.json
    id_i, ang = dados['id'], dados.get('angulo', 0)
    
    nome_proc = db_imagens[id_i]['processada']
    path_proc = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_proc)
    if os.path.exists(path_proc):
        img_p = cv2.imread(path_proc)
        img_p = aplicar_rotacao_cv2(img_p, ang)
        cv2.imwrite(path_proc, img_p)

    nome_orig = db_imagens[id_i]['original']
    path_orig = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_orig)
    if os.path.exists(path_orig) and nome_orig != nome_proc:
        img_o = cv2.imread(path_orig)
        img_o = aplicar_rotacao_cv2(img_o, ang)
        cv2.imwrite(path_orig, img_o)

    return jsonify({'sucesso': True, 'url': f"/uploads/{nome_proc}"})

@api_bp.route('/reajustar', methods=['POST'])
def reajustar():
    dados = request.json
    id_i, pts = dados['id'], np.array(dados['pontos'], dtype="float32")
    
    path_orig = os.path.join(current_app.config['UPLOAD_FOLDER'], db_imagens[id_i]['original'])
    img = cv2.imread(path_orig)
    
    cortada = processador.aplicar_perspectiva(img, processador.ordenar_pontos(pts))
    _, path_f = processador.salvar_resultado(path_orig, cortada)
    
    db_imagens[id_i]['processada'] = os.path.basename(path_f)
    return jsonify({'sucesso': True, 'url': f"/uploads/{db_imagens[id_i]['processada']}"})

@api_bp.route('/salvar_documento', methods=['POST'])
def salvar_documento():
    dados = request.json
    imgs_para_pdf = []
    for id_img in dados['ids']:
        if id_img in db_imagens:
            caminho_arquivo = os.path.join(current_app.config['UPLOAD_FOLDER'], db_imagens[id_img]['processada'])
            if os.path.exists(caminho_arquivo): imgs_para_pdf.append(Image.open(caminho_arquivo).convert('RGB'))
                
    if not imgs_para_pdf: return jsonify({'sucesso': False, 'erro': 'Nenhuma imagem válida para PDF.'}), 400
    nome = f"{dados['codigo']}_{dados['tipo']} Cosampa.pdf"
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], f"{uuid4().hex[:5]}_{nome}")
    imgs_para_pdf[0].save(path, save_all=True, append_images=imgs_para_pdf[1:])
    pdfs_gerados.append({'nome': nome, 'caminho': path})
    return jsonify({'sucesso': True})

# --- ROTA DE SALVAMENTO ATUALIZADA (Lidando com Múltiplas Tabelas) ---
@api_bp.route('/salvar_nuvem', methods=['POST'])
def salvar_nuvem():
    dados = request.json
    codigo = dados.get('codigo')
    nome_obra = dados.get('nome_obra') 
    status_global = dados.get('status_global', 'PENDENTE') # Novo Status Dinâmico
    secoes_front = dados.get('secoes', [])                 # Novas Gavetas
    documentos = dados.get('documentos', [])
    projeto_id = dados.get('projeto_id') 
    
    if not codigo or not documentos: return jsonify({'sucesso': False, 'erro': 'Sem dados.'}), 400
        
    try:
        # 1. Cria ou Atualiza o PROJETO
        if projeto_id:
            projeto = Projeto.query.get(projeto_id)
            if projeto:
                projeto.codigo_obra = codigo
                projeto.status_global = status_global
                if nome_obra: projeto.nome_obra = nome_obra
            else:
                projeto = Projeto(id=projeto_id, codigo_obra=codigo, nome_obra=nome_obra, status_global=status_global)
                db.session.add(projeto)
        else:
            projeto = Projeto(codigo_obra=codigo, nome_obra=nome_obra, status_global=status_global)
            db.session.add(projeto)
            
        db.session.flush() # Garante que temos o projeto.id gerado
        
        # 2. Atualiza as SEÇÕES (Limpa e recria para evitar duplicatas ocultas)
        SecaoProjeto.query.filter_by(projeto_id=projeto.id).delete()
        for sec in secoes_front:
            nova_secao = SecaoProjeto(
                projeto_id=projeto.id,
                nome_secao=sec['nome_secao'],
                status_secao=sec['status_secao'],
                observacao=sec['observacao']
            )
            db.session.add(nova_secao)
        
        # 3. Atualiza os DOCUMENTOS (Fotos/PDFs)
        ids_mantidos = [d['id'] for d in documentos]
        if ids_mantidos:
            Documento.query.filter(Documento.projeto_id == projeto.id, Documento.id.notin_(ids_mantidos)).delete(synchronize_session=False)
        else:
            Documento.query.filter(Documento.projeto_id == projeto.id).delete()
        
        for doc_front in documentos:
            id_img = doc_front['id']
            categoria = doc_front['categoria']
            ordem = doc_front['ordem']
            is_manual = doc_front.get('is_manual', False)
            
            doc_db = Documento.query.filter_by(id=id_img).first()
            
            if doc_db:
                doc_db.categoria = categoria
                doc_db.ordem_pagina = ordem
                doc_db.is_upload_manual = is_manual
                if id_img in db_imagens:
                    caminho_temp_proc = os.path.join(current_app.config['UPLOAD_FOLDER'], db_imagens[id_img]['processada'])
                    caminho_def_proc = os.path.join(current_app.config['DRIVE_FOLDER'], doc_db.caminho_cortado)
                    if os.path.exists(caminho_temp_proc): shutil.copy(caminho_temp_proc, caminho_def_proc)
            else:
                if id_img in db_imagens:
                    nome_orig = db_imagens[id_img]['original']
                    nome_proc = db_imagens[id_img]['processada']
                    
                    novo_nome_orig = f"{projeto.id}_ORIG_{nome_orig}"
                    novo_nome_proc = f"{projeto.id}_PROC_{nome_proc}"
                    
                    caminho_temp_orig = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_orig)
                    caminho_temp_proc = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_proc)
                    
                    if os.path.exists(caminho_temp_orig): shutil.copy(caminho_temp_orig, os.path.join(current_app.config['DRIVE_FOLDER'], novo_nome_orig))
                    if os.path.exists(caminho_temp_proc): shutil.copy(caminho_temp_proc, os.path.join(current_app.config['DRIVE_FOLDER'], novo_nome_proc))
                    
                    novo_doc = Documento(
                        id=id_img, 
                        projeto_id=projeto.id, 
                        caminho_original=novo_nome_orig, 
                        caminho_cortado=novo_nome_proc, 
                        categoria=categoria, 
                        ordem_pagina=ordem,
                        is_upload_manual=is_manual
                    )
                    db.session.add(novo_doc)
        
        db.session.commit()
        return jsonify({'sucesso': True, 'novo_id_projeto': projeto.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'sucesso': False, 'erro': str(e)}), 500

@api_bp.route('/uploads/<filename>')
def media(filename): 
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@api_bp.route('/api/excluir_projeto/<projeto_id>', methods=['DELETE'])
def excluir_projeto(projeto_id):
    try:
        projeto = Projeto.query.get(projeto_id)
        if not projeto:
            return jsonify({'sucesso': False, 'erro': 'Projeto não encontrado'}), 404
        
        # O banco de dados cuida das tabelas (cascade="all, delete-orphan"), 
        # mas nós precisamos excluir os arquivos físicos do HD.
        for doc in projeto.documentos:
            caminho_orig = os.path.join(current_app.config['DRIVE_FOLDER'], doc.caminho_original)
            caminho_proc = os.path.join(current_app.config['DRIVE_FOLDER'], doc.caminho_cortado)
            if os.path.exists(caminho_orig): os.remove(caminho_orig)
            if os.path.exists(caminho_proc): os.remove(caminho_proc)
        
        # Agora sim apagamos o projeto (e o banco apaga o resto)
        db.session.delete(projeto)
        db.session.commit()
        
        return jsonify({'sucesso': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'sucesso': False, 'erro': str(e)}), 500

# ==========================================
# NOVAS ROTAS PARA CONTROLE DA FILA E DO ROBÔ
# ==========================================

@api_bp.route('/api/adicionar_fila', methods=['POST'])
def adicionar_fila():
    dados = request.json
    obras = dados.get('obras', [])
    adicionadas = 0
    
    for obra in obras:
        existe_na_fila = FilaProcessamento.query.filter_by(codigo_obra=obra['codigo']).first()
        ja_processado = Projeto.query.filter_by(codigo_obra=obra['codigo']).first()
        
        if not existe_na_fila and not ja_processado:
            data_limite_val = None
            if 'data_iso' in obra:
                data_limite_val = datetime.strptime(obra['data_iso'], '%Y-%m-%d').date()
                
            nova_tarefa = FilaProcessamento(
                codigo_obra=obra['codigo'],
                nome_obra=obra['titulo_completo'],
                status_fila='AGUARDANDO',
                data_limite_runrunit=data_limite_val
            )
            db.session.add(nova_tarefa)
            adicionadas += 1
            
    db.session.commit()
    return jsonify({'sucesso': True, 'adicionadas': adicionadas})

@api_bp.route('/api/status_fila', methods=['GET'])
def status_fila():
    tarefas = FilaProcessamento.query.filter(FilaProcessamento.status_fila != 'SUCESSO').all()
    
    # ORDENAÇÃO INTELIGENTE NO SERVIDOR:
    # 1º PROCESSANDO fica no topo sempre (peso 0)
    # 2º Data de adição (ano 2000 vem primeiro, que é o nosso truque de prioridade)
    tarefas_ordenadas = sorted(tarefas, key=lambda t: (0 if t.status_fila == 'PROCESSANDO' else 1, t.data_adicao))
    
    lista_fila = []
    for t in tarefas_ordenadas:
        lista_fila.append({
            'codigo': t.codigo_obra,
            'status': t.status_fila,
            'erro': t.log_erro,
            'nome': t.nome_obra,
            'is_prioridade': t.data_adicao.year == 2000 # Avisa o HTML se foi priorizado
        })
        
    return jsonify({'sucesso': True, 'fila': lista_fila})

@api_bp.route('/api/limpar_fila', methods=['DELETE'])
def limpar_fila():
    try:
        FilaProcessamento.query.filter(FilaProcessamento.status_fila != 'PROCESSANDO').delete()
        db.session.commit()
        return jsonify({'sucesso': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'sucesso': False, 'erro': str(e)}), 500

# --- ROTAS DE PRIORIZAÇÃO ---
@api_bp.route('/api/priorizar', methods=['POST'])
def priorizar():
    dados = request.json
    codigo = dados.get('codigo')
    if not codigo: return jsonify({'sucesso': False})

    tarefa = FilaProcessamento.query.filter_by(codigo_obra=codigo).first()
    if tarefa:
        # Hack Elegante: Joga a data pro ano 2000 pro robô puxar primeiro
        tarefa.data_adicao = datetime(2000, 1, 1) 
    else:
        # Se você digitou um código novo que nem tava na fila, ele cria já com prioridade
        nova_tarefa = FilaProcessamento(
            codigo_obra=codigo,
            nome_obra=f"Busca Prioritária Manual",
            status_fila='AGUARDANDO',
            data_adicao=datetime(2000, 1, 1)
        )
        db.session.add(nova_tarefa)

    db.session.commit()
    return jsonify({'sucesso': True})

@api_bp.route('/api/cancelar_fila/<codigo>', methods=['DELETE'])
def cancelar_fila(codigo):
    try:
        tarefa = FilaProcessamento.query.filter_by(codigo_obra=codigo).first()
        if not tarefa:
            return jsonify({'sucesso': True, 'msg': 'Já não existia'})
            
        db.session.delete(tarefa)
        db.session.commit()
        return jsonify({'sucesso': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'sucesso': False, 'erro': str(e)})

# --- ROTAS DE PAUSA REAL DO ROBÔ ---
@api_bp.route('/api/status_robo', methods=['GET'])
def status_robo():
    config = ConfiguracaoSistema.query.filter_by(chave='status_robo').first()
    return jsonify({'sucesso': True, 'status': config.valor if config else 'RODANDO'})

@api_bp.route('/api/toggle_robo', methods=['POST'])
def toggle_robo():
    config = ConfiguracaoSistema.query.filter_by(chave='status_robo').first()
    if not config:
        config = ConfiguracaoSistema(chave='status_robo', valor='PAUSADO')
        db.session.add(config)
    else:
        config.valor = 'RODANDO' if config.valor == 'PAUSADO' else 'PAUSADO'
    db.session.commit()
    return jsonify({'sucesso': True, 'status': config.valor})