import os
import json
import base64
import asyncio
import logging
import httpx
from datetime import datetime
from fastapi import FastAPI, WebSocket, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import xml.etree.ElementTree as ET
import websockets

# Configuración
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración del servidor XMF
XMF_SERVER = "http://192.168.10.110:25000"

# Directorio de archivos
FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")

# Configuración
WEBSOCKET_URL = os.getenv("WEBSOCKET_URL", "ws://localhost:8000")

# Crear directorio de archivos si no existe
os.makedirs(FILES_DIR, exist_ok=True)

# FastAPI app
app = FastAPI()

# Templates
templates = Jinja2Templates(directory="templates")

class AgentWebSocket:
    def __init__(self):
        self.reconnect_delay = 5
        self.max_retries = 5
        self.is_connected = False
        self.last_message = None

    async def connect(self):
        """Establece la conexión WebSocket con el servidor"""
        while True:
            try:
                logger.info(" Conectando al servidor WebSocket...")
                async with websockets.connect(f"{WEBSOCKET_URL}/ws/agent") as websocket:
                    self.is_connected = True
                    logger.info(" Conexión WebSocket establecida")
                    await self.handle_messages(websocket)
                    
            except websockets.exceptions.WebSocketException as e:
                self.is_connected = False
                logger.error(f" Error en la conexión: {str(e)}")
            except Exception as e:
                self.is_connected = False
                logger.error(f" Error inesperado: {str(e)}")
            
            await asyncio.sleep(self.reconnect_delay)  # Esperar antes de reintentar

    async def handle_messages(self, websocket):
        try:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                
                # No mostrar el contenido del archivo en los logs
                log_data = data.copy() if isinstance(data, dict) else data
                if isinstance(log_data, dict) and 'content' in log_data:
                    log_data['content'] = '[CONTENT HIDDEN]'
                
                logger.info(f"📥 Mensaje recibido: {log_data}")
                self.last_message = json.dumps(log_data, indent=2)
                
                # Procesar el mensaje según su tipo
                if data.get("type") == "command":
                    response = await self.handle_command(data)
                    await websocket.send(json.dumps(response))
                
        except websockets.exceptions.ConnectionClosed:
            self.is_connected = False
            logger.info(" Conexión cerrada")
        except Exception as e:
            self.is_connected = False
            logger.error(f" Error manejando mensajes: {str(e)}")

    async def handle_command(self, data):
        """Maneja los comandos recibidos del servidor"""
        command = data.get("command")
        
        if command == "ping":
            return {"type": "response", "status": "ok", "message": "pong"}
            
        elif command == "download":
            try:
                filename = data.get("filename")
                content_b64 = data.get("content")
                
                if not filename or not content_b64:
                    return {
                        "type": "response",
                        "status": "error",
                        "message": "Missing filename or content"
                    }
                
                # Decodificar y guardar el archivo
                content = base64.b64decode(content_b64)
                file_path = os.path.join(FILES_DIR, filename)
                
                with open(file_path, 'wb') as f:
                    f.write(content)
                
                logger.info(f"✅ Archivo descargado: {filename}")
                return {
                    "type": "response",
                    "status": "success",
                    "message": f"File {filename} downloaded successfully"
                }
                
            except Exception as e:
                logger.error(f"❌ Error descargando archivo: {str(e)}")
                return {
                    "type": "response",
                    "status": "error",
                    "message": f"Error downloading file: {str(e)}"
                }
        
        elif command == "list_files":
            try:
                files = os.listdir(FILES_DIR)
                return {
                    "type": "agent_files",
                    "files": files
                }
            except Exception as e:
                logger.error(f"❌ Error listando archivos: {str(e)}")
                return {
                    "type": "response",
                    "status": "error",
                    "message": f"Error listing files: {str(e)}"
                }
        
        elif command == "delete_file":
            try:
                filename = data.get("filename")
                if not filename:
                    return {
                        "type": "response",
                        "status": "error",
                        "message": "Missing filename"
                    }
                
                file_path = os.path.join(FILES_DIR, filename)
                if not os.path.exists(file_path):
                    return {
                        "type": "response",
                        "status": "error",
                        "message": "File not found"
                    }
                
                os.remove(file_path)
                logger.info(f"✅ Archivo eliminado: {filename}")
                return {
                    "type": "response",
                    "status": "success",
                    "message": f"File {filename} deleted successfully"
                }
                
            except Exception as e:
                logger.error(f"❌ Error eliminando archivo: {str(e)}")
                return {
                    "type": "response",
                    "status": "error",
                    "message": f"Error deleting file: {str(e)}"
                }
        
        elif command == "get_know_devices":
            try:
                # Hacer la petición al servidor XMF
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        'http://localhost:8001/api/getKnowDevices',
                        headers={
                            "Content-Type": "application/vnd.cip4-jmf+xml",
                            "Accept": "application/xml"
                        }
                    )
                    if response.status_code == 200:
                        return {
                            "type": "response",
                            "status": "ok",
                            "command": command,
                            "data": response.text
                        }
                    else:
                        logger.error(f"Error del servidor XMF: {response.status_code} - {response.text}")
                        return {
                            "type": "response",
                            "status": "error",
                            "command": command,
                            "message": f"Error del servidor XMF: {response.status_code} - {response.text}"
                        }
            except Exception as e:
                logger.error(f"Error al conectar con el servidor XMF: {str(e)}")
                return {
                    "type": "response",
                    "status": "error",
                    "command": command,
                    "message": f"Error al conectar con el servidor XMF: {str(e)}"
                }
        
        else:
            return {"type": "response", "status": "error", "message": "Comando desconocido"}

# Instancia global del WebSocket
agent_ws = AgentWebSocket()

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/xmf", response_class=HTMLResponse)
async def xmf_page(request: Request):
    """Página para interactuar con el servidor XMF"""
    return templates.TemplateResponse("xmf.html", {"request": request})

@app.get("/status")
async def status():
    return {
        "websocket_connected": agent_ws.is_connected,
        "last_message": agent_ws.last_message
    }

@app.get("/list-files")
async def list_files():
    """Lista los archivos en el directorio de archivos"""
    try:
        files = os.listdir(FILES_DIR)
        return {"files": files}
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error listing files"}
        )

@app.delete("/files/{filename}")
async def delete_file(filename: str):
    """Elimina un archivo del directorio de archivos"""
    try:
        file_path = os.path.join(FILES_DIR, filename)
        if not os.path.exists(file_path):
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "File not found"}
            )
            
        os.remove(file_path)
        return {"status": "success", "message": "File deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting file {filename}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error deleting file"}
        )

@app.post("/api/getKnowDevices")
async def get_know_devices():
    """Endpoint para obtener KnowDevices del servidor XMF"""
    try:
        # Preparar el cuerpo XML
        current_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        request_body = f"""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<JMF xmlns="http://www.CIP4.org/JDFSchema_1_1"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     SenderID="MIS_ID"
     TimeStamp="{current_time}"
     Version="1.3">
  <Query Type="KnownDevices" ID="Q1"/>
</JMF>""".strip()

        # Configurar headers
        headers = {
            "Content-Type": "application/vnd.cip4-jmf+xml",
            "Accept": "application/xml",
            "User-Agent": "XMF Cyan"
        }

        # Realizar la solicitud al servidor XMF
        async with httpx.AsyncClient() as client:
            response = await client.post(
                XMF_SERVER,
                content=request_body,
                headers=headers,
                timeout=30.0  # Timeout de 30 segundos
            )

        # Verificar si la respuesta es exitosa
        response.raise_for_status()

        # Validar que la respuesta es XML válido
        try:
            ET.fromstring(response.text)
        except ET.ParseError as e:
            logger.error(f"Error parsing XML response: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Invalid XML response from XMF server"
            )

        # Devolver el XML como respuesta
        return Response(
            content=response.text,
            media_type="application/xml"
        )

    except httpx.RequestError as e:
        logger.error(f"Error connecting to XMF server: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to XMF server: {str(e)}"
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from XMF server: {str(e)}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"XMF server error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in getKnowDevices: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )

async def start_websocket():
    """Inicia la conexión WebSocket en segundo plano"""
    await agent_ws.connect()

@app.on_event("startup")
async def startup_event():
    """Se ejecuta cuando inicia la aplicación"""
    asyncio.create_task(start_websocket())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
