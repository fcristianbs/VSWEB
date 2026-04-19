import os
from sqlalchemy import create_engine, text

# 1. Caminho para o banco
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, "instance", "cosampa_drive.db")
engine = create_engine(f'sqlite:///{db_path}')

# 2. Update usando os nomes REAIS das colunas
with engine.connect() as connection:
    try:
        # Usando 'status_fila' e filtrando por 'codigo_obra'
        query = text("""
            UPDATE fila_processamento 
            SET status_fila = 'PENDENTE' 
            WHERE codigo_obra = :id_obra OR id = :id_obra
        """)
        
        result = connection.execute(query, {"id_obra": "8388052"})
        connection.commit()
        
        if result.rowcount > 0:
            print(f"✅ SUCESSO! {result.rowcount} registro(s) destravado(s) na 'fila_processamento'.")
            print("Pode atualizar seu painel, a obra deve estar disponível agora.")
        else:
            # Tentativa final caso o código de obra seja numérico no banco
            result_int = connection.execute(query, {"id_obra": 112601206})
            connection.commit()
            if result_int.rowcount > 0:
                print(f"✅ SUCESSO! Destravado (ID numérico).")
            else:
                print("⚠️ Não foi possível encontrar essa obra. Verifique se o código 112601206 está correto.")
            
    except Exception as e:
        print(f"❌ Erro ao atualizar: {e}")