# -*- coding: utf-8 -*-
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from enum import Enum
import uuid

class EstadoEntrega(str, Enum):
    pendiente = "pendiente"
    en_curso = "en_curso"
    completada = "completada"
    cancelada = "cancelada"

class EntregaCreate(BaseModel):
    cliente_id: uuid.UUID
    direccion_id: uuid.UUID
    descripcion: str
    bultos: int = 1
    peso_kg: Optional[float] = None
    fecha_estimada: Optional[date] = None
    observaciones: Optional[str] = None

class EntregaUpdate(BaseModel):
    direccion_id: Optional[uuid.UUID] = None
    descripcion: Optional[str] = None
    bultos: Optional[int] = None
    peso_kg: Optional[float] = None
    fecha_estimada: Optional[date] = None
    observaciones: Optional[str] = None

class EntregaResponse(BaseModel):
    id: uuid.UUID
    cliente_id: uuid.UUID
    cliente_nombre: Optional[str] = None
    direccion_id: uuid.UUID
    direccion_descripcion: Optional[str] = None
    ruta_id: Optional[uuid.UUID] = None
    descripcion: str
    bultos: int
    peso_kg: Optional[float] = None
    fecha_estimada: Optional[date] = None
    observaciones: Optional[str] = None
    observaciones_chofer: Optional[str] = None
    estado: EstadoEntrega
    creada_en: datetime
    actualizada_en: Optional[datetime] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_entrega(cls, entrega):
        return cls(
            id=entrega.id,
            cliente_id=entrega.cliente_id,
            cliente_nombre=entrega.cliente.nombre if entrega.cliente else None,
            direccion_id=entrega.direccion_id,
            direccion_descripcion=entrega.direccion.descripcion if entrega.direccion else None,
            ruta_id=entrega.ruta_id,
            descripcion=entrega.descripcion,
            bultos=entrega.bultos,
            peso_kg=entrega.peso_kg,
            fecha_estimada=entrega.fecha_estimada,
            observaciones=entrega.observaciones,
            observaciones_chofer=entrega.observaciones_chofer,
            estado=entrega.estado,
            creada_en=entrega.creada_en,
            actualizada_en=entrega.actualizada_en,
        )

class EntregaListResponse(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    entregas: List[EntregaResponse]