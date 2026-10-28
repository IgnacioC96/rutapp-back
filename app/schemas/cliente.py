# -*- coding: utf-8 -*-
"""
Schemas Pydantic para la gestión de clientes y sus direcciones.
Define los contratos de entrada y salida de la API para el módulo de clientes.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from app.core.geo import coordenadas_validas
from app.core.telefono import normalizar_telefono_ar
from typing import List, Optional
import uuid


class DireccionCreate(BaseModel):
    """
    Schema para crear o actualizar una dirección de cliente.
    El campo id es opcional — se usa al editar una dirección existente
    para identificarla y actualizarla en vez de eliminarla y recrearla.

    Sprint 3: se agregan latitud y longitud para que el front pueda
    enviar las coordenadas del pin que el admin fijó en el mapa.
    """
    # ID opcional — presente al editar, ausente al crear nueva dirección
    id: Optional[uuid.UUID] = None
    descripcion: str
    referencia: Optional[str] = None
    es_principal: bool = False
    # Sprint 3 — coordenadas del pin fijado en el mapa (opcionales)
    latitud: Optional[float] = Field(None, ge=-90, le=90)
    longitud: Optional[float] = Field(None, ge=-180, le=180)

    @field_validator("descripcion")
    @classmethod
    def _descripcion(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La dirección no puede estar vacía")
        return v

    @model_validator(mode="after")
    def _coordenadas(self):
        coordenadas_validas(self.latitud, self.longitud)
        return self


def validar_lista_direcciones(direcciones):
    """Reglas de negocio de las direcciones de un cliente (alta y edición)."""
    if len(direcciones) == 0:
        raise ValueError("Debe tener al menos una dirección")
    if len(direcciones) > 3:
        raise ValueError("Máximo 3 direcciones permitidas")
    principales = [d for d in direcciones if d.es_principal]
    if len(principales) != 1:
        raise ValueError("Debe haber exactamente una dirección principal")
    return direcciones


class DireccionResponse(BaseModel):
    """
    Respuesta de la API para una dirección de cliente.
    Incluye coordenadas para que el front pueda mostrar el pin en el mapa.
    """
    id: uuid.UUID
    descripcion: str
    referencia: Optional[str] = None
    es_principal: bool
    # Sprint 3 — coordenadas geocodificadas para el mapa
    latitud: Optional[float] = None
    longitud: Optional[float] = None

    class Config:
        from_attributes = True


def _normalizar_email(valor):
    """Vacío -> None; si viene, se guarda en minúsculas y sin espacios."""
    if valor is None:
        return None
    valor = valor.strip().lower()
    return valor or None


class ClienteCreate(BaseModel):
    """
    Body para POST /clientes — dar de alta un cliente nuevo.
    Debe tener entre 1 y 3 direcciones, exactamente una marcada como principal.
    """
    nombre: str
    # Se acepta en formato local (11 2345-6789) o internacional; se guarda como +549...
    telefono_whatsapp: str
    email: Optional[EmailStr] = None
    direcciones: List[DireccionCreate]
    cuit: Optional[str] = None
    notas: Optional[str] = None

    @field_validator("telefono_whatsapp")
    @classmethod
    def validar_telefono(cls, valor):
        return normalizar_telefono_ar(valor)

    @field_validator("email", mode="before")
    @classmethod
    def limpiar_email(cls, valor):
        return _normalizar_email(valor)

    @field_validator("direcciones")
    @classmethod
    def validar_direcciones(cls, direcciones):
        """Valida que las direcciones cumplan las reglas de negocio."""
        return validar_lista_direcciones(direcciones)


class ClienteUpdate(BaseModel):
    """
    Body para PUT /clientes/{id} — edición parcial de un cliente.
    Todos los campos son opcionales — solo se actualizan los que vienen.
    """
    nombre: Optional[str] = None
    telefono_whatsapp: Optional[str] = None
    email: Optional[EmailStr] = None
    direcciones: Optional[List[DireccionCreate]] = None
    cuit: Optional[str] = None
    notas: Optional[str] = None

    @field_validator("direcciones")
    @classmethod
    def validar_direcciones(cls, direcciones):
        """Si se mandan direcciones, deben cumplir las mismas reglas que en el alta."""
        return validar_lista_direcciones(direcciones) if direcciones is not None else None

    @field_validator("telefono_whatsapp")
    @classmethod
    def validar_telefono(cls, valor):
        return normalizar_telefono_ar(valor) if valor is not None else None

    @field_validator("email", mode="before")
    @classmethod
    def limpiar_email(cls, valor):
        return _normalizar_email(valor)


class ClienteResponse(BaseModel):
    """
    Respuesta completa de un cliente con sus direcciones.
    Usado en GET /clientes/{id}, POST /clientes y PUT /clientes/{id}.
    """
    id: uuid.UUID
    nombre: str
    telefono_whatsapp: str
    email: Optional[str] = None
    cuit: Optional[str] = None
    notas: Optional[str] = None
    activo: bool
    direcciones: List[DireccionResponse] = []

    class Config:
        from_attributes = True


class ClienteListResponse(BaseModel):
    """Respuesta paginada de GET /clientes."""
    total: int
    pagina: int
    por_pagina: int
    clientes: List[ClienteResponse]