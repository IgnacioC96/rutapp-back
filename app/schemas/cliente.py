# -*- coding: utf-8 -*-
from pydantic import BaseModel, field_validator
from typing import List, Optional
import uuid

class DireccionCreate(BaseModel):
    descripcion: str
    referencia: Optional[str] = None
    es_principal: bool = False

class DireccionResponse(BaseModel):
    id: uuid.UUID
    descripcion: str
    referencia: Optional[str] = None
    es_principal: bool

    class Config:
        from_attributes = True

class ClienteCreate(BaseModel):
    nombre: str
    telefono_whatsapp: str
    direcciones: List[DireccionCreate]
    cuit: Optional[str] = None
    notas: Optional[str] = None

    @field_validator("direcciones")
    @classmethod
    def validar_direcciones(cls, direcciones):
        if len(direcciones) == 0:
            raise ValueError("Debe tener al menos una direccion")
        if len(direcciones) > 3:
            raise ValueError("Maximo 3 direcciones permitidas")
        principales = [d for d in direcciones if d.es_principal]
        if len(principales) != 1:
            raise ValueError("Debe haber exactamente una direccion principal")
        return direcciones

class ClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    telefono_whatsapp: Optional[str] = None
    direcciones: Optional[List[DireccionCreate]] = None
    cuit: Optional[str] = None
    notas: Optional[str] = None

class ClienteResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    telefono_whatsapp: str
    cuit: Optional[str] = None
    notas: Optional[str] = None
    activo: bool
    direcciones: List[DireccionResponse] = []

    class Config:
        from_attributes = True

class ClienteListResponse(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    clientes: List[ClienteResponse]