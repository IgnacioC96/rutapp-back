from pydantic import BaseModel, EmailStr
from enum import Enum

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
    id: str
    nombre: str
    email: str
    rol: str
    telefono: str | None
    activo: bool

    class Config:
        from_attributes = True
