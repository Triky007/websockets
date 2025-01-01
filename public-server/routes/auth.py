"""
Rutas relacionadas con la autenticación y gestión de usuarios.
"""
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import UserCreate, UserUpdate
from ..auth import get_current_user, check_admin_role, create_access_token

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/login")
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Página de login"""
    current_user = await get_current_user(request, db)
    if current_user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "active_page": "login"
    })

@router.post("/login")
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Login de usuario"""
    try:
        user = db.query(User).filter(User.email == form_data.username).first()
        if not user or not user.verify_password(form_data.password):
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid email or password"},
                status_code=401
            )
        
        token = create_access_token(data={"sub": user.email})
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(
            key="token",
            value=f"Bearer {token}",
            httponly=True,
            max_age=3600,
            expires=3600
        )
        return response
        
    except Exception as e:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": str(e)},
            status_code=500
        )

@router.get("/logout")
async def logout():
    """Logout de usuario"""
    response = RedirectResponse(url="/login")
    response.delete_cookie("token")
    return response

@router.get("/register")
async def register_page(request: Request):
    """Página de registro"""
    return templates.TemplateResponse("register.html", {
        "request": request,
        "active_page": "register"
    })

@router.post("/register")
async def register(user: UserCreate, db: Session = Depends(get_db)):
    """Registro de usuario"""
    try:
        # Verificar si el email ya existe
        if db.query(User).filter(User.email == user.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Crear nuevo usuario
        new_user = User(
            email=user.email,
            role=UserRole.USER
        )
        new_user.set_password(user.password)
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        return RedirectResponse(url="/login", status_code=302)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Rutas de administración de usuarios
@router.get("/users")
async def users_page(
    request: Request,
    current_user: User = Depends(check_admin_role),
    db: Session = Depends(get_db)
):
    """Página de administración de usuarios"""
    users = db.query(User).all()
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "user": current_user,
        "active_page": "users"
    })

@router.get("/api/users")
async def list_users(
    current_user: User = Depends(check_admin_role),
    db: Session = Depends(get_db)
):
    """Lista todos los usuarios"""
    users = db.query(User).all()
    return [{"id": user.id, "email": user.email, "role": user.role} for user in users]

@router.delete("/api/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(check_admin_role),
    db: Session = Depends(get_db)
):
    """Elimina un usuario"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    db.delete(user)
    db.commit()
    return {"status": "success"}
