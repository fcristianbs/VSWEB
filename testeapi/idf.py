from google import genai
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Substitua pela sua chave
client = genai.Client(api_key=os.getenv("CHAVE_API_GEMINI"))

print("Modelos disponíveis para a sua API Key:")
print("-" * 40)

# Lista todos os modelos disponíveis
for model in client.models.list():
    # Filtra para mostrar apenas os que suportam geração de conteúdo
    if "generateContent" in model.supported_actions:
        print(model.name)
        
print("-" * 40)