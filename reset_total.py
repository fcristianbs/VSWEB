import sys
import os
import shutil

# Adiciona o diretório atual ao path para garantir as importações
sys.path.append(os.getcwd())

from app import app, db, DRIVE_FOLDER, UPLOAD_FOLDER, DOWNLOADS_GPM
from models import Projeto, Documento, SecaoProjeto, FilaProcessamento, LogSistema

def reset_sistema():
    print("\n" + "="*50)
    print("🚀 INICIANDO RESET TOTAL DO SISTEMA")
    print("="*50)
    
    with app.app_context():
        # 1. Limpar Tabelas do Banco
        print("\n📦 Etapa 1: Limpando Banco de Dados...")
        try:
            Documento.query.delete()
            SecaoProjeto.query.delete()
            Projeto.query.delete()
            FilaProcessamento.query.delete()
            LogSistema.query.delete()
            db.session.commit()
            print("✅ Tabelas limpas com sucesso.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Erro ao limpar banco: {e}")
        
        # 2. Limpar Arquivos Físicos
        print("\n📂 Etapa 2: Apagando arquivos físicos...")
        pastas = [DRIVE_FOLDER, UPLOAD_FOLDER, DOWNLOADS_GPM]
        for pasta in pastas:
            if not os.path.exists(pasta):
                print(f"⚠️ Pasta não encontrada: {pasta}")
                continue
            
            print(f"🧹 Limpando: {pasta}")
            cont_arquivos = 0
            for filename in os.listdir(pasta):
                file_path = os.path.join(pasta, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                    cont_arquivos += 1
                except Exception as e:
                    print(f'   - Falha ao deletar {filename}: {e}')
            print(f"   Done! {cont_arquivos} itens removidos.")
        
        print("\n" + "="*50)
        print("✨ RESET CONCLUÍDO!")
        print("="*50)
        print("\nPróximos passos:")
        print("1. Inicie o robô: python cloudprocess.py")
        print("2. Inicie o site: python app.py")
        print("\nO robô irá minerar os últimos 3 meses automaticamente.\n")

if __name__ == "__main__":
    print("\n❗ AVISO CRÍTICO: Isso apagará TODOS os dados processados e arquivos locais.")
    confirmacao = input("Digite 'sim' para confirmar a destruição total dos dados: ")
    
    if confirmacao.lower() == 'sim':
        reset_sistema()
    else:
        print("\n❌ Operação cancelada pelo usuário.")
