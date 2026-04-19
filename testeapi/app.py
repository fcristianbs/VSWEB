from google import genai
import PIL.Image
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# 1. Configuração do Cliente
client = genai.Client(api_key=os.getenv("CHAVE_API_GEMINI"))

# 2. Carregue a imagem
img = PIL.Image.open('C:\\Temp\\VSWEB\\testeapi\\0adaf5da-f3a4-435b-a693-92227a5aaa69_orig.jpg')

# 3. Gere o conteúdo com o modelo válido da sua lista
response = client.models.generate_content(
    model="gemini-2.5-flash", 
    contents=["Descreva esta imagem detalhadamente.", img]
)

# 4. Exiba o resultado
print("-" * 30)
print(response.text)
print("-" * 30)