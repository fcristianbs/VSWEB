import os
import zipfile
import shutil
from uuid import uuid4

def processar_zip_gpm(caminho_zip, pasta_destino):
    """
    Extrai todas as imagens de um ZIP, ignorando a estrutura de subpastas,
    e retorna uma lista com os novos nomes de arquivos.
    """
    imagens_extraidas = []
    
    if not os.path.exists(caminho_zip):
        return imagens_extraidas

    with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
        for info in zip_ref.infolist():
            # Ignora diretórios e arquivos que não são imagens
            if info.is_dir() or not info.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            
            # Gera um ID único para evitar conflito de nomes de fotos de obras diferentes
            ext = os.path.splitext(info.filename)[1]
            novo_nome = f"{uuid4().hex}{ext}"
            caminho_final = os.path.join(pasta_destino, novo_nome)
            
            # Extrai o conteúdo do arquivo e salva diretamente na pasta de destino (sem as subpastas)
            with zip_ref.open(info.filename) as source, open(caminho_final, "wb") as target:
                shutil.copyfileobj(source, target)
            
            imagens_extraidas.append(novo_nome)
            
    return imagens_extraidas