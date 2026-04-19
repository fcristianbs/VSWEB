from google import genai
import PIL.Image

# 1. Configuração do Cliente
client = genai.Client(api_key="AIzaSyA2HdAhtIkhj0Fya6lnLBUii6mg0kd5GZY")

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