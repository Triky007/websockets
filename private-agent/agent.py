import os
import requests
import asyncio
import json
import logging
import websockets
from dotenv import load_dotenv

# --- Cargar Variables desde .env ---
load_dotenv()  # Carga las variables desde el archivo .env

# --- Configuración General ---
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
WS_SERVER_URL = os.getenv("WS_SERVER_URL", "ws://localhost:8000/ws")
API_KEY = os.getenv("API_KEY", "your-secret-api-key")

# --- Configuración de Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

logger.info(f"SERVER_URL: {SERVER_URL}")
logger.info(f"WS_SERVER_URL: {WS_SERVER_URL}")
logger.info(f"API_KEY: {API_KEY}")

class DownloadAgent:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.download_queue = asyncio.Queue()
        self.session = requests.Session()  # Usar una sesión para mantener las cookies

    # --- Conexión WebSocket ---
    async def connect(self):
        while True:
            try:
                # Primero obtener el token
                logger.info("🔑 Obteniendo token de autenticación...")
                response = self.session.post(
                    f"{SERVER_URL}/token",
                    data={
                        "username": "admin@example.com",
                        "password": "admin123"
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"❌ Error al obtener token: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    await asyncio.sleep(5)
                    continue

                # Verificar que tenemos la cookie
                cookies = self.session.cookies
                logger.info(f"🍪 Cookies recibidas: {[f'{c.name}={c.value}' for c in cookies]}")
                
                if "access_token" not in self.session.cookies:
                    logger.error("❌ No se encontró el token en las cookies")
                    await asyncio.sleep(5)
                    continue
                
                # Obtener el token y limpiarlo de comillas extra
                token_cookie = next((c for c in cookies if c.name == "access_token"), None)
                if token_cookie:
                    token_value = token_cookie.value.strip('"')  # Eliminar comillas
                    logger.info(f"🔑 Token limpio: {token_value[:50]}...")
                    
                    # Construir el header de cookies manualmente
                    cookie_header = f"access_token={token_value}"
                    logger.info(f"🔒 Cookie header: {cookie_header}")
                    
                    # Conectar al WebSocket con el token
                    logger.info(f"🌐 Intentando conectar a {WS_SERVER_URL}")
                    headers = {"Cookie": cookie_header}
                    logger.info(f"📨 Headers de conexión: {headers}")
                    
                    async with websockets.connect(WS_SERVER_URL, extra_headers=headers) as websocket:
                        self.ws = websocket
                        self.connected = True
                        logger.info("✅ Conexión WebSocket establecida con el servidor.")
                        await self.handle_messages()
                else:
                    logger.error("❌ No se pudo obtener el token de las cookies")
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"❌ Error en la conexión WebSocket: {str(e)}")
                self.connected = False
                await asyncio.sleep(5)  # Reintento tras 5 segundos

    # --- Manejar Mensajes WebSocket ---
    async def handle_messages(self):
        try:
            while True:
                message = await self.ws.recv()
                data = json.loads(message)
                logger.info(f"📥 Mensaje recibido: {data}")
                
                if data.get("type") == "download":
                    file_name = data.get("file")
                    if file_name:
                        await self.download_file(file_name)
                    else:
                        logger.error("❌ Comando de descarga sin 'file' especificado.")
        except Exception as e:
            logger.error(f"❌ Error manejando mensajes WebSocket: {str(e)}")
            self.connected = False
            await asyncio.sleep(5)

    # --- Descargar Archivo ---
    async def download_file(self, file_name: str):
        try:
            logger.info(f"⬇️ Iniciando descarga de {file_name} desde el servidor...")
            
            # Usar la sesión existente que ya tiene las cookies
            response = self.session.get(
                f"{SERVER_URL}/secure-file/{file_name}",
                headers={"X-API-Key": API_KEY},
                stream=True
            )
            
            if response.status_code == 200:
                # Usar ruta absoluta para evitar problemas de permisos
                files_dir = os.path.abspath("files")
                os.makedirs(files_dir, exist_ok=True)  # Asegurar que la carpeta exista
                
                file_path = os.path.join(files_dir, file_name)
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                logger.info(f"✅ Archivo descargado correctamente: {file_name}")
                
                # Notificar al servidor que la descarga fue exitosa
                await self.ws.send(json.dumps({
                    "type": "download_complete",
                    "file": file_name
                }))
                logger.info(f"📤 Notificación de descarga enviada para: {file_name}")
            else:
                logger.error(f"❌ Error al descargar {file_name}: {response.status_code}")
                await self.ws.send(json.dumps({
                    "type": "download_failed",
                    "file": file_name,
                    "error": f"HTTP {response.status_code}"
                }))
        except Exception as e:
            logger.error(f"❌ Error durante la descarga de {file_name}: {str(e)}")
            if self.ws:
                await self.ws.send(json.dumps({
                    "type": "download_failed",
                    "file": file_name,
                    "error": str(e)
                }))

    # --- Listar Archivos Locales ---
    async def list_files(self):
        try:
            files_dir = os.path.abspath("files")
            os.makedirs(files_dir, exist_ok=True)
            files = [f for f in os.listdir(files_dir) if os.path.isfile(os.path.join(files_dir, f))]
            return {"files": files}
        except Exception as e:
            logger.error(f"❌ Error al listar archivos locales: {str(e)}")
            return {"files": []}

# --- Inicializar el Agente ---
agent = DownloadAgent()

# --- Iniciar la Aplicación FastAPI ---
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

app = FastAPI()

# Montar archivos estáticos y templates
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/files", StaticFiles(directory="files"), name="files")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(agent.connect())

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/list-files")
async def list_files():
    files_dir = os.path.abspath("files")
    if not os.path.exists(files_dir):
        return {"files": []}
    files = [f for f in os.listdir(files_dir) if os.path.isfile(os.path.join(files_dir, f))]
    return {"files": files}

@app.post("/download/{file_name}")
async def download_file(file_name: str):
    await agent.download_file(file_name)
    return {"status": "Download started"}

@app.delete("/files/{file_name}")
async def delete_file(file_name: str):
    try:
        file_path = os.path.join("files", file_name)
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"status": "File deleted"}
        return {"status": "File not found"}
    except Exception as e:
        return {"status": "Error", "detail": str(e)}

# --- Ejecutar el Servidor ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
