from selenium.webdriver import Chrome
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import requests
import datetime
import re
import json
import os
import time
import zipfile
import uuid

class MotorGPM:
    def __init__(self, usuario, senha, codigo, diretorio_base, callback_log):
        self.usuario = usuario
        self.senha = senha
        self.codigo = str(codigo)
        self.diretorio = diretorio_base
        self.callback = callback_log
        self.cookies = {}

    def autenticar(self):
        """Abre o navegador, faz o login UMA VEZ, salva os cookies e fecha o navegador."""
        try:
            self.callback("🔑 Iniciando navegador para Login único...")
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            options.add_argument("--log-level=3") 
            
            self.driver = Chrome(service=Service(), options=options)
            self.login(self.usuario, self.senha)
            self.driver.quit()
            
            self.callback("🔓 Autenticação concluída! Cookies salvos na memória.")
            return True
        except Exception as e:
            if hasattr(self, 'driver'):
                self.driver.quit()
            self.callback(f"❌ Erro na autenticação inicial: {str(e)}")
            return False

    def baixar_obra_api(self, codigo_obra):
        """Usa os cookies já salvos para baixar a obra via API (sem abrir navegador)"""
        self.codigo = str(codigo_obra)
        self.callback(f"🔎 Pesquisando obra {self.codigo} via API...")
        self.get_fotos_obras(self.codigo)

    def rodar(self):
        """Função mantida para compatibilidade com a busca manual no app.py"""
        try:
            self.callback("🚀 Iniciando automação (Busca Manual)...")
            if self.autenticar():
                self.baixar_obra_api(self.codigo)
        except Exception as e:
            self.callback(f"❌ Erro na automação: {str(e)}")

    def enter(self):
        action = ActionChains(self.driver)
        try:
            action.send_keys(Keys.ENTER)
            action.pause(1)
            action.perform()
            action.reset_actions()
        except:
            action.reset_actions()
            raise ValueError("Erro ao executar 'Keys.ENTER'")
            
    def login(self, username:str, password:str):
        self.driver.get("https://cosampa.gpm.srv.br")
        time.sleep(2) 
        self.driver.find_element("css selector", "input#idLogin").send_keys(username)
        self.driver.find_element("css selector", "input#idSenha").send_keys(password)
        self.enter()
        time.sleep(2) 
        self.get_cookies()
        
    def get_cookies(self):
        cookies = self.driver.get_cookies()
        self.cookies = { cookie['name']:cookie['value'] for cookie in cookies }

    def pesquisar_obra(self, value:str):
        url=r"https://cosampa.gpm.srv.br/ci/Servico/ConsultaFoto/listObras"
        data={"value":value}
        
        response = requests.post(url, data=data, cookies=self.cookies, timeout=30)
        
        if response.status_code == 200:
            try:
                dados = response.json()
                if len(dados) > 0:
                    self.obra = dados[0]
            except Exception as e:
                print("\n" + "="*50)
                print("❌ ERRO: GPM NÃO RETORNOU JSON NA PESQUISA ❌")
                print(f"URL: {response.url}")
                print(f"Status Code: {response.status_code}")
                print(f"Resposta bruta (500 chars):\n{response.text[:500]}")
                print("="*50 + "\n")
                
                if "login" in response.text.lower() or response.status_code == 401:
                    raise ValueError("SESSAO_EXPIRADA")
                else:
                    raise ValueError("O GPM respondeu com uma página inválida.")
        else:
            raise ValueError(f"Erro HTTP {response.status_code} ao pesquisar obra.")

    def pesquisar_servicos_obra(self, cod):
        url=r"https://cosampa.gpm.srv.br/ci/Servico/ConsultaFoto/consultaPaginada"
        params = {
            "draw": "1", "start": "0", "length": "50",
            "search[regex]": "false", "obras": f"{cod}",
            "_": f"{int(datetime.datetime.now().timestamp() * 1000)}"
        }
        
        response = requests.get(url, params=params, cookies=self.cookies, timeout=30)
        match = re.search(r'\{.*\}', response.text)
        if not match:
            print("\n" + "="*50)
            print("❌ ERRO: GPM NÃO RETORNOU SERVIÇOS ❌")
            print(f"Resposta bruta:\n{response.text[:500]}")
            print("="*50 + "\n")
            raise ValueError("Não foi possível extrair a lista de documentos da obra.")
            
        try:
            self.servicos = json.loads(match.group(0))
        except Exception:
            raise ValueError("O texto retornado pelo GPM na pesquisa de serviços está corrompido.")
        
    def get_fotos_obras(self, obra:str):
        self.obra_pesquisada = obra
        self.pesquisar_obra(obra)
        
        if not hasattr(self, 'obra'):
            raise ValueError(f"A obra {obra} não retornou resultados ou não existe.")
            
        self.callback("⚙️ Mapeando todos os serviços e fotos da obra...")
        self.pesquisar_servicos_obra(self.obra['value'])
        
        todos_servicos = [str(i[1]) for i in self.servicos['data']]
        if not todos_servicos:
            raise ValueError("Nenhum serviço/foto encontrado para esta obra.")

        tamanho_lote = 40 
        lotes = [todos_servicos[i:i + tamanho_lote] for i in range(0, len(todos_servicos), tamanho_lote)]
        
        zips_baixados = []
        
        headers_download = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate"
        }

        for idx, lote in enumerate(lotes):
            self.callback(f"📦 Solicitando Lote {idx+1}/{len(lotes)} ({len(lote)} fotos) ao servidor...")
            
            servisos_i = [f'"{s}":[]' for s in lote]
            fotos_api  = "{" + ','.join(servisos_i) + "}"
            cod_api    = ','.join(lote)

            url_processar = r"https://cosampa.gpm.srv.br/ci/Servico/ConsultaFoto/processarFotos"
            req_proc = requests.post(url_processar, data={"fotos": fotos_api, "cod": cod_api}, cookies=self.cookies, timeout=60)
            if req_proc.status_code != 200: raise ValueError(f"Erro HTTP {req_proc.status_code} ao processar lote {idx+1}.")
            
            try:
                fotos_json = req_proc.json()
            except Exception:
                raise ValueError(f"GPM falhou ao gerar o lote {idx+1}. Retornou HTML em vez de JSON.")
            
            data_baixar = { f"lista[{k}][]": fotos_json[k] for k in fotos_json }
            url_baixar = r"https://cosampa.gpm.srv.br/ci/Servico/ConsultaFoto/baixarFotos"
            req_baixar = requests.post(url_baixar, data=data_baixar, cookies=self.cookies, timeout=60)
            if req_baixar.status_code != 200: raise ValueError(f"Erro HTTP {req_baixar.status_code} ao pedir o ZIP do lote {idx+1}.")
            
            try:
                arquivo_servidor = req_baixar.json()['arquivo']
            except Exception:
                raise ValueError(f"GPM falhou ao empacotar o ZIP no servidor. Lote {idx+1} corrompido.")
            
            self.callback(f"📥 Baixando Lote {idx+1}/{len(lotes)}...")
            url_down = f"https://cosampa.gpm.srv.br/ci/Servico/ConsultaFoto/downloadZip/{arquivo_servidor}"
            nome_zip_lote = f"temp_lote_{idx}_{obra}.zip"
            caminho_lote = os.path.join(self.diretorio, nome_zip_lote)
            
            with requests.post(url_down, cookies=self.cookies, headers=headers_download, stream=True, timeout=60) as resp_down:
                with open(caminho_lote, "wb") as f:
                    for chunk in resp_down.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                        
            zips_baixados.append(caminho_lote)
            time.sleep(1) 
            
        self.callback("🗜️ Consolidando todos os lotes...")
        nome_final = f"LOTE_MÁSTER_{obra}.zip"
        caminho_final = os.path.join(self.diretorio, nome_final)
        
        with zipfile.ZipFile(caminho_final, 'w') as zip_master:
            for zip_temp in zips_baixados:
                with zipfile.ZipFile(zip_temp, 'r') as z_lote:
                    for item in z_lote.infolist():
                        conteudo = z_lote.read(item.filename)
                        novo_nome_interno = f"{uuid.uuid4().hex[:5]}_{item.filename}"
                        zip_master.writestr(novo_nome_interno, conteudo)
                        
        for zip_temp in zips_baixados:
            if os.path.exists(zip_temp):
                os.remove(zip_temp)

        self.callback(f"✅ Download concluído: {nome_final}")