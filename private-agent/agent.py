import os
import requests
import asyncio
import json
import logging
import websockets

# --- Configuración de Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configuración General ---
SERVER_URL = os.getenv("SERVER_URL", "http://public-server:8000")
WS_SERVER_URL = os.getenv("WS_SERVER_URL", "ws://public-server:8000/ws")
API_KEY = os.getenv("API_KEY", "your-secret-api-key")

class DownloadAgent:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.download_queue = asyncio.Queue()

    # --- Conexión WebSocket ---
    async def connect(self):
        while True:
            try:
                logger.info(f"🌐 Intentando conectar a {WS_SERVER_URL}")
                async with websockets.connect(WS_SERVER_URL) as websocket:
                    self.ws = websocket
                    self.connected = True
                    logger.info("✅ Conexión WebSocket establecida con el servidor.")
                    await self.handle_messages()
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
            
            response = requests.get(
                f"{SERVER_URL}/secure-file/{file_name}",
                headers={"api-key": API_KEY},
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
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

app = FastAPI()

# Montar archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# --- Rutas HTTP ---
@app.on_event("startup")
async def startup_event():
    # Crear carpeta de archivos si no existe
    os.makedirs("files", exist_ok=True)
    # Iniciar WebSocket en segundo plano
    asyncio.create_task(agent.connect())

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/list-files")
async def list_files():
    return await agent.list_files()

@app.get("/download/{file_name}")
async def download_file(file_name: str):
    file_path = os.path.join("files", file_name)
    if not os.path.exists(file_path):
        logger.error(f"❌ Archivo no encontrado para descarga: {file_name}")
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

@app.delete("/delete/{file_name}")
async def delete_file(file_name: str):
    file_path = os.path.join("files", file_name)
    if not os.path.exists(file_path):
        logger.error(f"❌ Archivo no encontrado para eliminación: {file_name}")
        raise HTTPException(status_code=404, detail="File not found")
    try:
        os.remove(file_path)
        logger.info(f"🗑️ Archivo eliminado correctamente: {file_name}")
        return {"status": "File deleted"}
    except Exception as e:
        logger.error(f"❌ Error eliminando archivo {file_name}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting file")

# --- Ejecutar el Servidor ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
