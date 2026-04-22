import sys
import os
from datetime import datetime, timedelta

# Adiciona o diretório atual ao path para importar app e models
sys.path.append(os.getcwd())

from app import app
from models import db, FilaProcessamento

with app.app_context():
    total = FilaProcessamento.query.count()
    nao_sucesso = FilaProcessamento.query.filter(FilaProcessamento.status_fila != 'SUCESSO').count()
    processando = FilaProcessamento.query.filter(FilaProcessamento.status_fila == 'PROCESSANDO').count()
    aguardando = FilaProcessamento.query.filter(FilaProcessamento.status_fila == 'AGUARDANDO').count()
    
    print(f"Total: {total}")
    print(f"Nao Sucesso: {nao_sucesso}")
    print(f"Processando: {processando}")
    print(f"Aguardando: {aguardando}")
    
    # Amostra das datas
    amostra = FilaProcessamento.query.limit(5).all()
    for item in amostra:
        print(f"ID: {item.id}, Codigo: {item.codigo_obra}, Status: {item.status_fila}, Data: {item.data_adicao}")
