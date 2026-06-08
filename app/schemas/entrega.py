from pydantic import BaseModel
from typing import Optional
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
    id: str
    cliente_id: str
    direccion_id: str
    ruta_id: Optional[str]
    descripcion: str
    bultos: int
    peso_kg: Optional[float]
    fecha_estimada: Optional[date]
    observaciones: Optional[str]
    observaciones_chofer: Optional[str]
    estado: EstadoEntrega
    creada_en: datetime
    actualizada_en: Optional[datetime]

    class Config:
        from_attributes = True

class EntregaListResponse(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    entregas: list[EntregaResponse]
