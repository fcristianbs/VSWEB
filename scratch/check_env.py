import os
from dotenv import load_dotenv

print("Current working directory:", os.getcwd())
print(".env exists:", os.path.exists(".env"))
print(".env.example exists:", os.path.exists(".env.example"))

load_dotenv()
key = os.getenv("CHAVE_API_GEMINI")
print("CHAVE_API_GEMINI found:", "Yes" if key else "No")
if key:
    print("Key length:", len(key))
    print("Key starts with:", key[:5])
