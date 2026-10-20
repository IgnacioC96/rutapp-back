from pydantic import BaseModel, EmailStr, field_validator
from app.core.password import validar_fortaleza_password
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

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validar_fortaleza_password(v)


class CambiarPassword(BaseModel):
    password_actual: str
    password_nueva: str

    @field_validator("password_nueva")
    @classmethod
    def _nueva(cls, v: str) -> str:
        return validar_fortaleza_password(v)


class UsuarioResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    email: str
    rol: str
    telefono: Optional[str] = None
    activo: bool

    class Config:
        from_attributes = True
