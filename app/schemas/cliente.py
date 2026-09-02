# -*- coding: utf-8 -*-
"""
Schemas Pydantic para la gestión de clientes y sus direcciones.
Define los contratos de entrada y salida de la API para el módulo de clientes.
"""
from pydantic import BaseModel, field_validator
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
    latitud: Optional[float] = None
    longitud: Optional[float] = None


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


class ClienteCreate(BaseModel):
    """
    Body para POST /clientes — dar de alta un cliente nuevo.
    Debe tener entre 1 y 3 direcciones, exactamente una marcada como principal.
    """
    nombre: str
    telefono_whatsapp: str
    direcciones: List[DireccionCreate]
    cuit: Optional[str] = None
    notas: Optional[str] = None

    @field_validator("direcciones")
    @classmethod
    def validar_direcciones(cls, direcciones):
        """Valida que las direcciones cumplan las reglas de negocio."""
        if len(direcciones) == 0:
            raise ValueError("Debe tener al menos una dirección")
        if len(direcciones) > 3:
            raise ValueError("Máximo 3 direcciones permitidas")
        principales = [d for d in direcciones if d.es_principal]
        if len(principales) != 1:
            raise ValueError("Debe haber exactamente una dirección principal")
        return direcciones


class ClienteUpdate(BaseModel):
    """
    Body para PUT /clientes/{id} — edición parcial de un cliente.
    Todos los campos son opcionales — solo se actualizan los que vienen.
    """
    nombre: Optional[str] = None
    telefono_whatsapp: Optional[str] = None
    direcciones: Optional[List[DireccionCreate]] = None
    cuit: Optional[str] = None
    notas: Optional[str] = None


class ClienteResponse(BaseModel):
    """
    Respuesta completa de un cliente con sus direcciones.
    Usado en GET /clientes/{id}, POST /clientes y PUT /clientes/{id}.
    """
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
    """Respuesta paginada de GET /clientes."""
    total: int
    pagina: int
    por_pagina: int
    clientes: List[ClienteResponse]