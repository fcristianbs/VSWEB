import cv2
import numpy as np
import os
import PIL.Image
from google import genai
import time 

from dotenv import load_dotenv

load_dotenv('C:\\Temp\\VSWEB\\VSWEB\\.env.example')
# --- CONFIGURAÇÃO DA API ---
CHAVE_API_GEMINI = os.getenv("CHAVE_API_GEMINI") 

try:
    client = genai.Client(api_key=CHAVE_API_GEMINI)
except Exception as e:
    print(f"Erro ao iniciar cliente Gemini: {e}")
    client = None

def classificar_com_gemini(caminho_imagem):
    """Envia a imagem original para o Gemini."""
    if not client:
        return "DOCUMENTO" 

    prompt = (
        "Você é um classificador automático. "
        "REGRA DE OURO: Se existir QUALQUER folha de papel, caderno, formulário ou prancheta em destaque na imagem, você DEVE ignorar completamente o fundo (mesmo que seja banco de carro, chão ou mesa) e classificar como documento. "
        "Responda APENAS com UMA das seguintes palavras, sem explicações:\n"
        "- APR : Se conseguir ler 'Análise Preliminar de Risco' no papel.\n"
        "- PI : Se conseguir ler 'Plano de Intervenção' no papel.\n"
        "- ENTREGA : Se tratar de uma 'Entrega de Trabalho'.\n"
        "- PLANO AT/MT : Se tratar de um 'Plano de trabalho para rede desenergizada AT/MT'.\n"
        "- PROJETO : Se tratar de um 'Projeto de eletrificação' ou 'Projeto de obra'.\n"
        "- AUTORIZAÇÃO : Se tratar de uma 'Autorização de trabalho rede energizada'.\n"
        "- DOCUMENTO : Se for claramente uma folha de papel/caderno, mas não for nenhum dos títulos acima.\n"
        "- FOTOS : APENAS se NÃO houver nenhum papel em destaque (ex: postes, ruas, equipamentos de obra) tome cuidado para não confundir o cartão de informação no canto da imagens(em fotos de rua) com um documento."
    )

    try:
        img = PIL.Image.open(caminho_imagem)
    except Exception as e:
        return "FOTOS" 

    # ESTRATÉGIA DE ALTA DISPONIBILIDADE: Fallback + Backoff Exponencial
    modelos_para_tentar = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    max_tentativas = 4
    espera_base = 5 # Segundos

    for tentativa in range(max_tentativas):
        modelo_atual = modelos_para_tentar[tentativa % len(modelos_para_tentar)]
        
        try:
            response = client.models.generate_content(
                model=modelo_atual, 
                contents=[prompt, img]
            )
            resposta_ia = response.text.strip().upper()
            
            categorias_validas = [
                "APR", "PI", "ENTREGA", "PLANO AT/MT", "PROJETO", "AUTORIZAÇÃO", "DOCUMENTO", "FOTOS"
            ]
            
            for tipo in categorias_validas:
                if tipo in resposta_ia:
                    return tipo
            return "FOTOS" 
            
        except Exception as e:
            erro_str = str(e)
            
            if "429" in erro_str or "RESOURCE_EXHAUSTED" in erro_str or "503" in erro_str or "UNAVAILABLE" in erro_str:
                espera = espera_base * (2 ** tentativa)  
                print(f"⚠️ Servidor lotado ({modelo_atual}). Pausando robô por {espera}s... (Tentativa {tentativa+1}/{max_tentativas})")
                time.sleep(espera) 
            else:
                print(f"❌ Erro de processamento na IA: {erro_str}")
                return "FOTOS" 
                
    print("⚠️ Desistindo após 4 tentativas. Classificando como FOTO.")
    return "FOTOS"

# --- FUNÇÕES AUXILIARES DE RECORTE ---

def ordenar_pontos(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)] 
    rect[2] = pts[np.argmax(s)] 
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)] 
    rect[3] = pts[np.argmax(diff)] 
    return rect

def aplicar_perspectiva(img, pts):
    rect = ordenar_pontos(pts)
    (tl, tr, br, bl) = rect
    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))
    heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxHeight = max(int(heightA), int(heightB))
    dst = np.array([[0, 0], [maxWidth - 1, 0], [maxWidth - 1, maxHeight - 1], [0, maxHeight - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))
    return warped

def salvar_resultado(caminho_orig, img_final):
    dir_name = os.path.dirname(caminho_orig)
    base_name = os.path.basename(caminho_orig)
    caminho_final = os.path.join(dir_name, f"SCAN_OK_{base_name}")
    cv2.imwrite(caminho_final, img_final)
    return True, caminho_final

# --- O FLUXO PRINCIPAL ---
def recortar_caderno_preciso(caminho_imagem):
    img = cv2.imread(caminho_imagem)
    if img is None: 
        return False, caminho_imagem, "FOTOS"
        
    orig = img.copy()

    tipo_ia = classificar_com_gemini(caminho_imagem)
    is_doc = tipo_ia != "FOTOS"

    if not is_doc:
        _, caminho_final = salvar_resultado(caminho_imagem, orig)
        return False, caminho_final, tipo_ia

    area_total = img.shape[0] * img.shape[1]
    ratio = img.shape[0] / 500.0
    img_resized = cv2.resize(img, (int(img.shape[1] / ratio), 500))

    gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(gray_blur, 50, 150)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel)

    cnts, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]

    doc_cnt = None
    for c in cnts:
        peri = cv2.arcLength(c, True)
        for eps in np.linspace(0.01, 0.08, 10):
            approx = cv2.approxPolyDP(c, eps * peri, True)
            if len(approx) == 4:
                area_contorno_real = cv2.contourArea(approx) * (ratio ** 2)
                if area_contorno_real > (area_total * 0.10):
                    doc_cnt = approx
                    break 
        if doc_cnt is not None:
            break

    if doc_cnt is not None:
        pts_reais = doc_cnt.reshape(4, 2) * ratio
        warped = aplicar_perspectiva(orig, pts_reais)
        _, caminho_final = salvar_resultado(caminho_imagem, warped)
    else:
        _, caminho_final = salvar_resultado(caminho_imagem, orig)

    return is_doc, caminho_final, tipo_ia