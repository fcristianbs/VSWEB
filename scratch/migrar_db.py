import sqlite3
import os

db_path = 'instance/cosampa_drive.db'
if not os.path.exists(db_path):
    db_path = 'cosampa_drive.db'

print(f"Tentando atualizar banco em: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Adiciona colunas se não existirem
    try:
        cursor.execute("ALTER TABLE projetos ADD COLUMN data_obra DATE")
        print("Coluna data_obra adicionada em 'projetos'")
    except sqlite3.OperationalError:
        print("Coluna data_obra já existe em 'projetos'")

    try:
        cursor.execute("ALTER TABLE fila_processamento ADD COLUMN etapa VARCHAR(50)")
        cursor.execute("ALTER TABLE fila_processamento ADD COLUMN dados_checkpoint TEXT")
        print("Colunas de checkpoint adicionadas em 'fila_processamento'")
    except sqlite3.OperationalError:
        print("Colunas de checkpoint já existem ou erro ao adicionar")

    # Tabela de logs (create_all do SQLAlchemy cuidará disso se não existir, 
    # mas garantimos aqui)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs_sistema (
        id VARCHAR(36) PRIMARY KEY,
        mensagem TEXT NOT NULL,
        nivel VARCHAR(20) DEFAULT 'INFO',
        data_evento DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    print("Tabela 'logs_sistema' verificada/criada.")

    conn.commit()
    conn.close()
    print("Atualização concluída com sucesso!")
except Exception as e:
    print(f"Erro ao atualizar banco: {e}")
