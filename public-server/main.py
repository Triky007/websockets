# main.py
from fastapi import FastAPI, WebSocket, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import os
import logging
from typing import Optional
import json
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()
API_KEY = os.getenv("API_KEY", "default-secret-key")

# Configurar logging
logging.basicConfig(
    filename="uvicorn.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Montar archivos estáticos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "files")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(FILES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Almacenar agentes conectados
connected_agents = set()


# 🛡️ Verificar API Key
def verify_api_key(api_key: str = Header(None)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


# 🏠 Ruta principal
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# 🌐 WebSocket para Comunicación en Tiempo Real
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_agents.add(websocket)
    logger.info("Agent connected via WebSocket")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("type") == "download_complete":
                    file_name = message.get("file")
                    logger.info(f"Download completed: {file_name}")
                    for agent in list(connected_agents):
                        try:
                            await agent.send_json({
                                "type": "status_update",
                                "status": "done",
                                "file": file_name
                            })
                        except Exception as e:
                            logger.error(f"Error sending status update: {str(e)}")
                            connected_agents.remove(agent)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {data}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        connected_agents.remove(websocket)
        logger.info("Agent disconnected from WebSocket")


# 📄 Listar Archivos Disponibles
@app.get("/list-files")
async def list_files():
    if not os.path.exists(FILES_DIR):
        return {"files": []}
    files = [f for f in os.listdir(FILES_DIR) if os.path.isfile(os.path.join(FILES_DIR, f))]
    logger.info("File list requested")
    return {"files": files}


# 📥 Iniciar Descarga de Archivo
@app.post("/start-download/{file_name}")
async def start_download(file_name: str):
    file_path = os.path.join(FILES_DIR, file_name)
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_name}")
        raise HTTPException(status_code=404, detail="File not found")
    
    # Enviar comando de descarga a los agentes conectados
    for agent in list(connected_agents):
        try:
            await agent.send_json({
                "type": "download",
                "file": file_name
            })
            logger.info(f"Download command sent for {file_name}")
        except Exception as e:
            logger.error(f"Failed to send download command: {str(e)}")
            connected_agents.remove(agent)
    
    return {"status": "Download started"}


# 🔒 Descarga Segura de Archivo
@app.get("/secure-file/{file_name}")
async def get_secure_file(file_name: str, api_key: str = Depends(verify_api_key)):
    file_path = os.path.join(FILES_DIR, file_name)
    if not os.path.exists(file_path):
        logger.error(f"Secure file not found: {file_name}")
        raise HTTPException(status_code=404, detail="File not found")
    logger.info(f"Secure file access: {file_name}")
    return FileResponse(file_path)


# 🚀 Iniciar Servidor
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
