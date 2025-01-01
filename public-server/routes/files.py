"""
Rutas relacionadas con la gestión de archivos.
"""
from fastapi import APIRouter, Depends, Request, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
import uuid
import aiofiles
from datetime import datetime

from ..database import get_db
from ..auth import get_current_user
from ..models import FileUpload

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Directorio de archivos
FILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "files")

@router.get("/files")
async def list_files(request: Request, db: Session = Depends(get_db)):
    """Lista los archivos disponibles"""
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login")

    # Obtener archivos del directorio
    files = []
    if os.path.exists(FILES_DIR):
        for filename in os.listdir(FILES_DIR):
            file_path = os.path.join(FILES_DIR, filename)
            if os.path.isfile(file_path):
                file_info = {
                    "name": filename,
                    "size": os.path.getsize(file_path),
                    "modified": datetime.fromtimestamp(os.path.getmtime(file_path))
                }
                files.append(file_info)

    return templates.TemplateResponse("files.html", {
        "request": request,
        "files": files,
        "user": current_user,
        "active_page": "files"
    })

@router.post("/upload")
async def upload_files(
    request: Request, 
    file: UploadFile = File(..., description="File to upload", max_size=100 * 1024 * 1024),  # 100MB límite
    db: Session = Depends(get_db)
):
    """Sube un archivo al servidor"""
    try:
        current_user = await get_current_user(request, db)
        if not current_user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        # Crear directorio si no existe
        os.makedirs(FILES_DIR, exist_ok=True)

        # Generar nombre único para el archivo
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(FILES_DIR, unique_filename)

        # Guardar archivo
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)

        # Registrar en base de datos
        file_upload = FileUpload(
            filename=unique_filename,
            original_name=file.filename,
            user_id=current_user.id
        )
        db.add(file_upload)
        db.commit()

        return {"filename": unique_filename, "original_name": file.filename}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/files/{filename}")
async def delete_files(filename: str, request: Request, db: Session = Depends(get_db)):
    """Elimina un archivo del servidor"""
    try:
        current_user = await get_current_user(request, db)
        if not current_user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        file_path = os.path.join(FILES_DIR, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        os.remove(file_path)
        
        # Eliminar registro de la base de datos
        file_upload = db.query(FileUpload).filter(FileUpload.filename == filename).first()
        if file_upload:
            db.delete(file_upload)
            db.commit()

        return {"status": "success", "message": "File deleted successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
