from fastapi import FastAPI, WebSocket, HTTPException, Depends, Header, status, Request, Response, Query, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
import logging
import json
import os
import models
import database
import websockets
import auth
from datetime import timedelta
from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
from database import SessionLocal, engine, Base
from dotenv import load_dotenv
from fastapi.security import OAuth2PasswordRequestForm
import base64
from starlette.websockets import WebSocketDisconnect

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear tablas en la base de datos
models.Base.metadata.create_all(bind=engine)

# Cargar variables de entorno
load_dotenv()
API_KEY = os.getenv("API_KEY", "default-secret-key")
SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# Crear directorios necesarios
os.makedirs("files", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar archivos estáticos y plantillas
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Incluir rutas de autenticación
app.include_router(auth.router)

# Modelo para la creación de usuarios
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None

# Rutas públicas
@app.get("/")
async def root(request: Request, db: Session = Depends(database.get_db)):
    try:
        current_user = await auth.get_current_user(request, db)
        if current_user:
            return RedirectResponse(url="/dashboard")
    except:
        pass
    return RedirectResponse(url="/login")

@app.get("/login")
async def login_page(request: Request, db: Session = Depends(database.get_db)):
    try:
        current_user = await auth.get_current_user(request, db)
        if current_user:
            return RedirectResponse(url="/dashboard")
    except:
        pass
    return templates.TemplateResponse("login.html", {"request": request, "user": None})

@app.post("/login")
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db)
):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Incorrect username or password", "user": None},
            status_code=401
        )

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=1800,
        expires=1800,
    )
    return response

@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

@app.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db)
):
    logger.info(f"🔑 Intento de login para: {form_data.username}")
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        logger.error(f"❌ Credenciales inválidas para: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    logger.info(f"✅ Token generado para: {user.email}")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(user: UserCreate, db: Session = Depends(database.get_db)):
    # Verificar si el usuario ya existe
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Crear nuevo usuario
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        role=models.UserRole.USER  # Por defecto, crear usuarios normales
    )
    
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return {"message": "User created successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# Rutas protegidas
@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(database.get_db)):
    try:
        # Validar el token y obtener el usuario
        current_user = await auth.get_current_user(request, db)
        
        if not current_user:
            logger.warning("No authenticated user for dashboard")
            return RedirectResponse(url="/login")
            
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "user": current_user,
            "active_page": "dashboard"
        })
    except Exception as e:
        logger.error(f"Error in dashboard: {str(e)}")
        return RedirectResponse(url="/login")

@app.get("/users")
async def users_page(
    request: Request,
    current_user: models.User = Depends(auth.check_admin_role),
    db: Session = Depends(database.get_db)
):
    users = db.query(models.User).all()
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "user": current_user,
        "active_page": "users"
    })

@app.get("/users-management")
async def users_management_page(
    request: Request,
    current_user: models.User = Depends(auth.check_admin_role)
):
    return templates.TemplateResponse("users-management.html", {
        "request": request,
        "user": current_user
    })

@app.get("/api/users")
async def list_users(
    current_user: models.User = Depends(auth.check_admin_role),
    db: Session = Depends(database.get_db)
):
    users = db.query(models.User).all()
    return [{"id": user.id, "email": user.email, "role": user.role, "is_active": user.is_active} for user in users]

@app.delete("/api/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: models.User = Depends(auth.check_admin_role),
    db: Session = Depends(database.get_db)
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        db.delete(db_user)
        db.commit()
        return {"message": "User deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/list-files")
async def list_files(request: Request, db: Session = Depends(database.get_db)):
    """Lista los archivos en el directorio files"""
    try:
        logger.info("Listing files...")
        current_user = await auth.get_current_user(request, db)
        
        if not current_user:
            logger.warning("User not authenticated for listing files")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
            
        logger.info(f"User {current_user.email} requesting file list")
        
        # Asegurar que el directorio existe
        if not os.path.exists(FILES_DIR):
            os.makedirs(FILES_DIR)
            logger.info(f"Created files directory: {FILES_DIR}")
            return {"files": []}
            
        # Listar archivos
        try:
            files = [f for f in os.listdir(FILES_DIR) if os.path.isfile(os.path.join(FILES_DIR, f))]
            logger.info(f"Found {len(files)} files: {files}")
            return {"files": files}
        except Exception as e:
            logger.error(f"Error reading directory: {str(e)}")
            return {"files": [], "error": str(e)}
            
    except HTTPException as e:
        logger.error(f"HTTP error listing files: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing files: {str(e)}"
        )

@app.post("/start-download/{file_name}")
async def start_download(
    request: Request,
    file_name: str,
    db: Session = Depends(database.get_db)
):
    current_user = await auth.get_current_user(request, db)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
        
    file_path = os.path.join("files", file_name)
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_name}")
        raise HTTPException(status_code=404, detail="File not found")
    
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

@app.get("/secure-file/{file_name}")
async def get_secure_file(
    request: Request,
    file_name: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(database.get_db)
):
    current_user = await auth.get_current_user(request, db)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
        
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    file_path = os.path.join("files", file_name)
    if not os.path.exists(file_path):
        logger.error(f"Secure file not found: {file_name}")
        raise HTTPException(status_code=404, detail="File not found")
    logger.info(f"Secure file access: {file_name}")
    return FileResponse(file_path)

@app.get("/agent-files")
async def agent_files(request: Request, db: Session = Depends(database.get_db)):
    """Página para ver los archivos del agente"""
    try:
        current_user = await auth.get_current_user(request, db)
        if not current_user:
            return RedirectResponse(url="/login")
            
        return templates.TemplateResponse("agent_files.html", {
            "request": request,
            "user": current_user
        })
    except Exception as e:
        logger.error(f"❌ Error en agent_files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/agent-files")
async def agent_files_page(
    request: Request,
    current_user: models.User = Depends(auth.check_admin_role)
):
    return templates.TemplateResponse("agent_files.html", {
        "request": request,
        "user": current_user
    })

@app.get("/xmf")
async def xmf_page(request: Request, db: Session = Depends(database.get_db)):
    """Página para interactuar con el servidor XMF a través del agente"""
    current_user = await auth.get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("xmf.html", {
        "request": request,
        "user": current_user,
        "active_page": "xmf"
    })

FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")

@app.post("/download/{filename}")
async def download_file(filename: str, request: Request, db: Session = Depends(database.get_db)):
    """Envía comando de descarga al agente"""
    try:
        current_user = await auth.get_current_user(request, db)
        if not current_user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        file_path = os.path.join(FILES_DIR, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        # Leer el contenido del archivo
        with open(file_path, 'rb') as f:
            file_content = f.read()
            file_content_b64 = base64.b64encode(file_content).decode('utf-8')

        if not connected_agents:
            raise HTTPException(status_code=503, detail="No agents connected")

        # Enviar comando de descarga a todos los agentes conectados
        success = False
        for agent in connected_agents:
            try:
                await agent.send_json({
                    "type": "command",
                    "command": "download",
                    "filename": filename,
                    "content": file_content_b64
                })
                logger.info(f"✅ Comando de descarga enviado para {filename}")
                success = True
            except Exception as e:
                logger.error(f"❌ Error enviando comando al agente: {str(e)}")
                continue

        if not success:
            raise HTTPException(status_code=503, detail="Failed to send download command to any agent")

        return {"status": "success", "message": "Download command sent"}
    except Exception as e:
        logger.error(f"❌ Error en descarga: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload_files")
async def upload_files(
    request: Request, 
    file: UploadFile = File(..., description="File to upload", max_size=100 * 1024 * 1024),  # 100MB límite
    db: Session = Depends(database.get_db)
):
    """Sube un archivo al servidor"""
    try:
        current_user = await auth.get_current_user(request, db)
        if not current_user:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        # Asegurar que el directorio existe
        if not os.path.exists(FILES_DIR):
            os.makedirs(FILES_DIR)
        
        # Verificar el tamaño del archivo
        file_size = 0
        content = bytearray()
        
        # Leer el archivo en chunks para manejar archivos grandes
        chunk_size = 1024 * 1024  # 1MB chunks
        async for chunk in file.stream():
            content.extend(chunk)
            file_size += len(chunk)
            if file_size > 100 * 1024 * 1024:  # 100MB límite
                raise HTTPException(
                    status_code=413,
                    detail="File too large. Maximum size allowed is 100MB"
                )
        
        # Guardar el archivo en el directorio files del servidor
        file_path = os.path.join(FILES_DIR, file.filename)
        with open(file_path, "wb") as f:
            f.write(content)
            
        logger.info(f"✅ Archivo subido: {file.filename} ({file_size / 1024 / 1024:.2f}MB)")
        
        # Verificar si la petición espera JSON o HTML
        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            return {"status": "success", "message": "File uploaded successfully"}
        else:
            return RedirectResponse(url="/dashboard", status_code=303)
        
    except HTTPException as e:
        logger.error(f"❌ Error subiendo archivo: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"❌ Error subiendo archivo: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/delete_files/{filename}")
async def delete_files(filename: str, request: Request, db: Session = Depends(database.get_db)):
    """Elimina un archivo del servidor"""
    try:
        current_user = await auth.get_current_user(request, db)
        if not current_user:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        file_path = os.path.join(FILES_DIR, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
            
        os.remove(file_path)
        logger.info(f"✅ Archivo eliminado: {filename}")
        return {"status": "success", "message": "File deleted successfully"}
        
    except Exception as e:
        logger.error(f"❌ Error eliminando archivo: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Lista de conexiones WebSocket de clientes web
connected_clients = set()

async def send_websocket_message(websocket: WebSocket, message: dict, remove_from: set = None):
    """Envía un mensaje por WebSocket de forma segura"""
    try:
        # Convertir el mensaje a JSON y verificar su tamaño
        message_str = json.dumps(message)
        if len(message_str) > 1024 * 1024:  # 1MB límite
            logger.warning(f"❌ Mensaje demasiado grande ({len(message_str)} bytes)")
            # Enviar solo un resumen del mensaje
            summary = {
                "type": message.get("type", "unknown"),
                "status": message.get("status", "error"),
                "message": "Message too large to send"
            }
            await websocket.send_json(summary)
        else:
            await websocket.send_json(message)
        return True
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje por WebSocket: {str(e)}")
        if remove_from and websocket in remove_from:
            remove_from.remove(websocket)
        return False

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Endpoint WebSocket para clientes web"""
    try:
        await websocket.accept()
        connected_clients.add(websocket)
        logger.info("✅ Cliente web conectado")
        
        # Enviar estado inicial del agente
        await send_websocket_message(websocket, {
            "type": "agent_status",
            "connected": len(connected_agents) > 0
        })
        logger.info(f"📤 Estado inicial del agente enviado: {len(connected_agents) > 0}")
        
        try:
            while True:
                data = await websocket.receive_json()
                logger.info(f"📥 Mensaje de cliente web: {data}")
                
                # Reenviar comando a todos los agentes conectados
                if not connected_agents:
                    logger.info("❌ No hay agentes conectados")
                    await send_websocket_message(websocket, {
                        "type": "error",
                        "message": "No hay agentes conectados"
                    })
                    continue
                
                success = False
                for agent in list(connected_agents):  # Usar una copia para evitar modificar durante la iteración
                    if await send_websocket_message(agent, data, connected_agents):
                        success = True
                        logger.info("✅ Comando enviado al agente")
                
                if not success:
                    logger.error("❌ No se pudo enviar el comando a ningún agente")
                    await send_websocket_message(websocket, {
                        "type": "error",
                        "message": "No se pudo enviar el comando a ningún agente"
                    })
                    
        except WebSocketDisconnect:
            logger.info("❌ Cliente web desconectado")
        finally:
            if websocket in connected_clients:
                connected_clients.remove(websocket)
    except Exception as e:
        logger.error(f"❌ Error en WebSocket de cliente web: {str(e)}")
        if websocket in connected_clients:
            connected_clients.remove(websocket)

@app.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    """WebSocket para el agente"""
    try:
        await websocket.accept()
        connected_agents.add(websocket)
        logger.info("✅ Agente conectado")
        
        try:
            while True:
                data = await websocket.receive_json()
                logger.info(f"📥 Mensaje del agente: {data}")
                
                # Reenviar respuesta a todos los clientes web conectados
                for client in list(connected_clients):  # Usar una copia para evitar modificar durante la iteración
                    await send_websocket_message(client, data, connected_clients)
                
                await send_websocket_message(websocket, {"status": "ok", "message": "Mensaje recibido"})
        except WebSocketDisconnect:
            logger.info("❌ Agente desconectado")
        finally:
            if websocket in connected_agents:
                connected_agents.remove(websocket)
    except Exception as e:
        logger.error(f"❌ Error en WebSocket del agente: {str(e)}")
        if websocket in connected_agents:
            connected_agents.remove(websocket)

# Almacenar agentes conectados
connected_agents = set()

@app.on_event("startup")
async def startup_event():
    """Se ejecuta cuando inicia la aplicación"""
    # Crear base de datos si no existe
    models.Base.metadata.create_all(bind=engine)
    
    # Crear usuarios por defecto
    db = SessionLocal()
    try:
        # Admin user
        admin_user = db.query(models.User).filter(models.User.email == "admin@example.com").first()
        if not admin_user:
            admin_user = models.User(
                email="admin@example.com",
                hashed_password=auth.get_password_hash("admin123"),
                role="admin"
            )
            db.add(admin_user)
            logger.info("✅ Usuario admin creado")
        
        # Agent user
        agent_user = db.query(models.User).filter(models.User.email == "agent@example.com").first()
        if not agent_user:
            agent_user = models.User(
                email="agent@example.com",
                hashed_password=auth.get_password_hash("agentpass123"),
                role="admin"  # El agente necesita ser admin para usar el WebSocket
            )
            db.add(agent_user)
            logger.info("✅ Usuario agente creado")
        
        db.commit()
        logger.info("✅ Base de datos inicializada")
    except Exception as e:
        logger.error(f"❌ Error inicializando la base de datos: {str(e)}")
    finally:
        db.close()

# Iniciar servidor
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
