from google import genai

# Substitua pela sua chave
client = genai.Client(api_key="AIzaSyA2HdAhtIkhj0Fya6lnLBUii6mg0kd5GZY")

print("Modelos disponíveis para a sua API Key:")
print("-" * 40)

# Lista todos os modelos disponíveis
for model in client.models.list():
    # Filtra para mostrar apenas os que suportam geração de conteúdo
    if "generateContent" in model.supported_actions:
        print(model.name)
        
print("-" * 40)