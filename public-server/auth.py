from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request, Cookie, APIRouter
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from database import get_db
from models import User, UserRole
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de seguridad
SECRET_KEY = "your-secret-key-keep-it-safe"  # En producción, usar una clave segura
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter()

async def get_token_from_cookie(request: Request) -> Optional[str]:
    authorization = request.cookies.get("access_token")
    logger.info(f"Cookie token: {authorization[:10] if authorization else None}")
    
    if not authorization:
        logger.warning("No token cookie found")
        return None
        
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            logger.warning(f"Invalid token scheme in cookie: {scheme}")
            return None
            
        logger.info(f"Valid token found in cookie: {token[:10]}...")
        return token
    except ValueError:
        logger.warning(f"Malformed token in cookie: {authorization}")
        return None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.info(f"Created token for user: {data.get('sub')} with role: {data.get('role')}")
    return encoded_jwt

async def get_current_user(request: Request = None, db: Session = Depends(get_db)):
    logger.info("Attempting to get current user")
    
    token = await get_token_from_cookie(request)
    if not token:
        logger.warning("No token found in cookie")
        return None
        
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        logger.info(f"Attempting to decode token: {token[:10]}...")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.info(f"Token payload: {payload}")
        
        email: str = payload.get("sub")
        if email is None:
            logger.warning("No email in token payload")
            raise credentials_exception
            
        logger.info(f"Token decoded successfully for email: {email}")
    except JWTError as e:
        logger.error(f"JWT decode error: {str(e)}")
        raise credentials_exception
    
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        logger.warning(f"No user found for email: {email}")
        raise credentials_exception
        
    logger.info(f"User found: {user.email}, role: {user.role}")
    return user

async def get_current_user_from_token(token: str, db: Session):
    try:
        logger.info(f"Attempting to decode token in get_current_user_from_token: {token[:10]}...")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.info(f"Token payload: {payload}")
        email: str = payload.get("sub")
        if email is None:
            logger.warning("No email in token payload")
            return None
        user = db.query(User).filter(User.email == email).first()
        if user:
            logger.info(f"User found: {user.email}")
        else:
            logger.warning(f"No user found for email: {email}")
        return user
    except JWTError as e:
        logger.error(f"JWT decode error in get_current_user_from_token: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_current_user_from_token: {str(e)}")
        return None

async def get_current_active_user(request: Request, current_user: User = Depends(get_current_user)):
    logger.info("Checking if user is active")
    
    if not current_user:
        logger.warning("No current user")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    if not current_user.is_active:
        logger.warning(f"User {current_user.email} is inactive")
        raise HTTPException(status_code=400, detail="Inactive user")
        
    logger.info(f"Active user confirmed: {current_user.email}")
    return current_user

def check_admin_role(current_user: User = Depends(get_current_user)):
    logger.info("Checking admin role")
    
    if not current_user:
        logger.warning("No current user for admin check")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    if current_user.role != UserRole.ADMIN:
        logger.warning(f"User {current_user.email} is not admin")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
        
    logger.info(f"Admin role confirmed for user: {current_user.email}")
    return current_user

from pydantic import BaseModel

class UserUpdate(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    password: str
    role: str = "user"

@router.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

@router.put("/api/users/{user_id}", response_model=dict)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logger.info(f"Updating user {user_id} with data: {user_update}")
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update users")

    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Actualizar rol si se proporciona
    if user_update.role is not None:
        if user_update.role not in ["user", "admin"]:
            raise HTTPException(status_code=400, detail="Invalid role")
        db_user.role = user_update.role

    # Actualizar contraseña si se proporciona
    if user_update.password:
        db_user.hashed_password = get_password_hash(user_update.password)

    try:
        db.commit()
        return {"message": "User updated successfully"}
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/users", response_model=dict)
async def create_user(
    user: UserCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logger.info(f"Creating new user with email: {user.email}")
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create users")

    # Verificar que el email no existe
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Verificar el rol
    if user.role not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role")

    # Crear el usuario
    db_user = User(
        email=user.email,
        hashed_password=get_password_hash(user.password),
        role=user.role
    )

    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return {"message": "User created successfully"}
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete users")

    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        db.delete(db_user)
        db.commit()
        return {"message": "User deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/users")
async def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can list users")

    users = db.query(User).all()
    return [
        {
            "id": user.id,
            "email": user.email,
            "role": user.role
        }
        for user in users
    ]
