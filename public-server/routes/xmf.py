"""
Rutas relacionadas con la funcionalidad XMF.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/xmf")
async def xmf_page(request: Request, db: Session = Depends(get_db)):
    """Página para interactuar con el servidor XMF a través del agente"""
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("xmf.html", {
        "request": request,
        "user": current_user,
        "active_page": "xmf"
    })
