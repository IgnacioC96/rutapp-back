from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum
import uuid

class RolUsuario(str, Enum):
    admin = "admin"
    chofer = "chofer"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    rol: RolUsuario

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    nombre: str

class UsuarioCreate(BaseModel):
    nombre: str
    email: EmailStr
    password: str
    rol: RolUsuario
    telefono: str | None = None

class UsuarioResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    email: str
    rol: str
    telefono: Optional[str] = None
    activo: bool

    class Config:
        from_attributes = True
