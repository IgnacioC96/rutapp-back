from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hashear_password(password: str) -> str:
    return pwd_context.hash(password)

def verificar_password(password_plano: str, password_hash: str) -> bool:
    return pwd_context.verify(password_plano, password_hash)

def crear_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def verificar_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None
    

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Define dÃ³nde espera FastAPI el token en cada request
# El front debe mandar: Authorization: Bearer <token>
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Dependency que se inyecta en cada endpoint protegido.
    Verifica el token JWT y devuelve los datos del usuario.
    Si el token es invÃ¡lido o expirÃ³, lanza 401 automÃ¡ticamente.
    """
    payload = verificar_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invÃ¡lido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

def require_admin(current_user: dict = Depends(get_current_user)):
    """
    Dependency que ademÃ¡s verifica que el usuario sea admin.
    Se usa en endpoints que solo puede acceder el rol admin.
    """
    if current_user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenÃ©s permisos para realizar esta acciÃ³n"
        )
    return current_user

def require_chofer(current_user: dict = Depends(get_current_user)):
    """
    Dependency que verifica que el usuario sea chofer.
    """
    if current_user.get("rol") != "chofer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los choferes pueden acceder a este recurso"
        )
    return current_user
