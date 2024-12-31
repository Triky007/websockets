from database import SessionLocal, engine
import models
from auth import get_password_hash
from models import User, UserRole

# Crear las tablas
models.Base.metadata.create_all(bind=engine)

def create_admin_user(email: str, password: str):
    db = SessionLocal()
    try:
        # Verificar si el usuario ya existe
        user = db.query(User).filter(User.email == email).first()
        if user:
            print(f"Usuario {email} ya existe")
            return

        # Crear nuevo usuario admin
        db_user = User(
            email=email,
            hashed_password=get_password_hash(password),
            role=UserRole.ADMIN
        )
        db.add(db_user)
        db.commit()
        print(f"Usuario administrador {email} creado exitosamente")
    finally:
        db.close()

if __name__ == "__main__":
    # Crear usuario admin
    create_admin_user("admin@example.com", "admin123")
