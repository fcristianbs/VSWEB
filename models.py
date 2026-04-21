from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

# Instancia o banco de dados
db = SQLAlchemy()

def gerar_uuid():
    """Gera um ID único e seguro"""
    return str(uuid.uuid4())

# ==========================================
# 1. TABELA PRINCIPAL DE PROJETOS
# ==========================================
class Projeto(db.Model):
    __tablename__ = 'projetos'
    
    id = db.Column(db.String(36), primary_key=True, default=gerar_uuid)
    codigo_obra = db.Column(db.String(50), nullable=False, unique=True)
    nome_obra = db.Column(db.String(200), nullable=True)
    
    # STATUS GLOBAL (PENDENTE ou CONCLUÍDO)
    status_global = db.Column(db.String(20), default='PENDENTE') 
    
    # Data limite para o Kanban e Data Real da Obra
    data_limite = db.Column(db.Date, nullable=True) 
    data_obra = db.Column(db.Date, nullable=True) # Data da execução (Runrun.it)
    
    data_criacao = db.Column(db.DateTime, default=datetime.now)
    data_ultima_edicao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # TRAVA DE SEGURANÇA 1: cascade="all, delete-orphan"
    # Se o projeto for apagado, apaga as seções e as fotos dele junto.
    secoes = db.relationship('SecaoProjeto', backref='projeto', lazy=True, cascade="all, delete-orphan")
    documentos = db.relationship('Documento', backref='projeto', lazy=True, cascade="all, delete-orphan")


# ==========================================
# 2. BLOCOS DE DOCUMENTOS (As "Gavetas")
# ==========================================
class SecaoProjeto(db.Model):
    __tablename__ = 'secoes_projeto'
    
    id = db.Column(db.String(36), primary_key=True, default=gerar_uuid)
    
    # TRAVA DE SEGURANÇA 2: nullable=False
    # É impossível uma seção existir sem estar amarrada a um projeto.
    projeto_id = db.Column(db.String(36), db.ForeignKey('projetos.id', ondelete='CASCADE'), nullable=False)
    
    nome_secao = db.Column(db.String(50), nullable=False) # Ex: 'APR', 'PI', 'ENTREGA'
    status_secao = db.Column(db.String(20), default='pendente') # 'pendente', 'analise', 'ok'
    observacao = db.Column(db.Text, nullable=True) 


# ==========================================
# 3. TABELA DE ARQUIVOS (Imagens/PDFs)
# ==========================================
class Documento(db.Model):
    __tablename__ = 'documentos'
    
    id = db.Column(db.String(36), primary_key=True, default=gerar_uuid)
    
    # TRAVA DE SEGURANÇA 3: nullable=False
    # É impossível uma foto ou PDF existir sem o ID do projeto dono.
    projeto_id = db.Column(db.String(36), db.ForeignKey('projetos.id', ondelete='CASCADE'), nullable=False) 
    
    caminho_original = db.Column(db.String(255), nullable=False)
    caminho_cortado = db.Column(db.String(255), nullable=True)
    categoria = db.Column(db.String(50), default='FOTOS') 
    ordem_pagina = db.Column(db.Integer, default=9000)
    
    # FLAG para pular a inteligência artificial
    is_upload_manual = db.Column(db.Boolean, default=False)


# ==========================================
# 4. A FILA DE PROCESSAMENTO (O Robô)
# ==========================================
class FilaProcessamento(db.Model):
    __tablename__ = 'fila_processamento'
    
    id = db.Column(db.String(36), primary_key=True, default=gerar_uuid)
    codigo_obra = db.Column(db.String(50), nullable=False, unique=True)
    nome_obra = db.Column(db.String(200), nullable=True)
    
    data_limite_runrunit = db.Column(db.Date, nullable=True) 
    data_obra = db.Column(db.Date, nullable=True) # Data da execução (Runrun.it)
    
    # Controle do Robô
    status_fila = db.Column(db.String(20), default='AGUARDANDO') # AGUARDANDO, PROCESSANDO, ERRO, SUCESSO
    etapa = db.Column(db.String(50), nullable=True) # BAIXANDO, EXTRAINDO, PROCESSANDO_IA
    dados_checkpoint = db.Column(db.Text, nullable=True) # JSON ou string com progresso (ex: "15/42")
    log_erro = db.Column(db.Text, nullable=True)
    
    data_adicao = db.Column(db.DateTime, default=datetime.now)


# ==========================================
# 5. CONFIGURAÇÃO GLOBAL (Botão de Pausa)
# ==========================================
class ConfiguracaoSistema(db.Model):
    __tablename__ = 'configuracoes_sistema'
    
    chave = db.Column(db.String(50), primary_key=True) # Ex: 'status_robo'
    valor = db.Column(db.String(50)) # Ex: 'RODANDO' ou 'PAUSADO'


# ==========================================
# 6. LOGS DO SISTEMA (Para o Painel Admin)
# ==========================================
class LogSistema(db.Model):
    __tablename__ = 'logs_sistema'
    
    id = db.Column(db.String(36), primary_key=True, default=gerar_uuid)
    mensagem = db.Column(db.Text, nullable=False)
    nivel = db.Column(db.String(20), default='INFO') # INFO, WARNING, ERROR, SUCESSO
    data_evento = db.Column(db.DateTime, default=datetime.now)