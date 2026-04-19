import os
import re

app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Extrair Imports e Configurações (Linha 1 a 40)
# Vamos recriar o app.py do zero.

novo_app = """import os
from flask import Flask
from models import db
from dotenv import load_dotenv

from extensions import db_imagens, pdfs_gerados, log_queue
from routes.web import web_bp
from routes.api import api_bp

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DOWNLOADS_GPM = os.path.join(BASE_DIR, 'downloads_gpm')
DRIVE_FOLDER = os.path.join(BASE_DIR, 'drive_local') 

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOADS_GPM'] = DOWNLOADS_GPM
app.config['DRIVE_FOLDER'] = DRIVE_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cosampa_drive.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

for pasta in [UPLOAD_FOLDER, DOWNLOADS_GPM, DRIVE_FOLDER]:
    if not os.path.exists(pasta): os.makedirs(pasta)

db.init_app(app)
with app.app_context():
    db.create_all()

# Registrar Blueprints
app.register_blueprint(web_bp)
app.register_blueprint(api_bp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
"""

# Extrair apenas a parte de rotas e Helpers (Linha 41 em diante)
linhas = content.splitlines()

api_bp_content = """import os, cv2, zipfile, numpy as np, threading, shutil
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

"""

capturando_api = False
bloco_atual = []

for i, linha in enumerate(linhas):
    # Começar a capturar a partir dos Auxiliares
    if "def aplicar_rotacao_cv2" in linha:
        capturando_api = True
    
    # Ignorar rotas WEB que já foram para web.py
    if "@app.route('/')" in linha or "@app.route('/drive')" in linha:
        capturando_api = False
        continue
    
    # Voltar a capturar rotas API
    if "@app.route('/api/carregar_projeto" in linha:
        capturando_api = True
    
    # Ignorar a inicialização do final
    if "if __name__ == '__main__':" in linha:
        capturando_api = False
        continue

    if capturando_api:
        # Substituições para Blueprint
        l = linha.replace("@app.route", "@api_bp.route")
        l = l.replace("app.config", "current_app.config")
        bloco_atual.append(l)

api_bp_content += "\\n".join(bloco_atual)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(novo_app)

os.makedirs("routes", exist_ok=True)
with open("routes/api.py", "w", encoding="utf-8") as f:
    f.write(api_bp_content)

print("Refatoração completa!")
