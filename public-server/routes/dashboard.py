"""
Rutas relacionadas con el dashboard y páginas principales.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/")
async def root(request: Request, db: Session = Depends(get_db)):
    """Página principal"""
    current_user = await get_current_user(request, db)
    if current_user:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")

@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Dashboard principal"""
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login")
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,
        "active_page": "dashboard"
    })
