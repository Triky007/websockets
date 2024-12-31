from fastapi import FastAPI, WebSocket, HTTPException, Depends, Header, status, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from typing import Optional
import json
from dotenv import load_dotenv
from database import engine, get_db
from sqlalchemy.orm import Session
import models
import auth
from datetime import timedelta

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear tablas en la base de datos
models.Base.metadata.create_all(bind=engine)

# Cargar variables de entorno
load_dotenv()
API_KEY = os.getenv("API_KEY", "default-secret-key")

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

# Rutas de autenticación
@app.post("/token")
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email, "role": user.role.value},
        expires_delta=access_token_expires
    )
    
    # Configurar la cookie con el token
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=False  # Cambiar a True en producción con HTTPS
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}

# Rutas públicas
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Rutas protegidas
@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        # Validar el token y obtener el usuario
        current_user = await auth.get_current_user(request, db)
        
        if not current_user:
            logger.warning("No authenticated user for dashboard")
            return RedirectResponse(url="/login")
            
        logger.info(f"User authenticated for dashboard: {current_user.email}")
        
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "user": current_user}
        )
    except Exception as e:
        logger.error(f"Error in dashboard access: {str(e)}")
        return RedirectResponse(url="/login")

@app.get("/list-files")
async def list_files(request: Request, db: Session = Depends(get_db)):
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
        
        # Usar ruta absoluta
        files_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")
        logger.info(f"Files directory: {files_dir}")
        
        if not os.path.exists(files_dir):
            logger.warning(f"Files directory does not exist: {files_dir}")
            return {"files": []}
            
        files = [f for f in os.listdir(files_dir) if os.path.isfile(os.path.join(files_dir, f))]
        logger.info(f"Found {len(files)} files: {files}")
        return {"files": files}
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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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

# WebSocket
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        # Obtener el token de las cookies
        cookies = websocket.headers.get("cookie", "")
        logger.info(f"WebSocket headers: {websocket.headers}")
        logger.info(f"WebSocket cookies received: {cookies}")
        
        token = None
        
        # Parsear las cookies manualmente
        if cookies:
            cookie_list = cookies.split("; ")
            logger.info(f"Cookie list: {cookie_list}")
            for cookie in cookie_list:
                if cookie.startswith("access_token="):
                    auth_token = cookie.split("=")[1]
                    # Extraer el token después de "Bearer "
                    try:
                        scheme, token = auth_token.split()
                        if scheme.lower() != "bearer":
                            logger.error(f"Invalid token scheme: {scheme}")
                            continue
                        logger.info(f"Found token in cookies: {token[:10]}...")
                    except ValueError:
                        logger.error(f"Malformed token: {auth_token}")
                        continue
                    break
        
        if not token:
            logger.error("No valid token found in cookies")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        try:
            db = next(get_db())
            logger.info("Attempting to validate token...")
            user = await auth.get_current_user_from_token(token, db)
            
            if not user:
                logger.error("Invalid token or user not found")
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            
            logger.info(f"WebSocket connection authenticated for user: {user.email}")
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()
        connected_agents.add(websocket)
        logger.info(f"Agent connected. Total agents: {len(connected_agents)}")

        while True:
            try:
                data = await websocket.receive_text()
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
                logger.error(f"WebSocket message error: {str(e)}")
                break
    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
    finally:
        if websocket in connected_agents:
            connected_agents.remove(websocket)
            logger.info(f"Agent disconnected. Remaining agents: {len(connected_agents)}")

# Almacenar agentes conectados
connected_agents = set()

# Iniciar servidor
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
