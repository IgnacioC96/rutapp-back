from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid

class EstadoRuta(str, Enum):
    pendiente = "pendiente"
    asignada = "asignada"
    en_curso = "en_curso"
    completada = "completada"
    finalizada = "finalizada"

class ParadaResponse(BaseModel):
    orden: int
    entrega_id: str
    cliente: str
    direccion: str
    tiempo_desde_anterior_min: Optional[int]
    distancia_desde_anterior_km: Optional[float]

    class Config:
        from_attributes = True

class RutaCreate(BaseModel):
    nombre: str
    entregas_ids: List[uuid.UUID]
    origen_descripcion: Optional[str] = None
    origen_latitud: Optional[float] = None
    origen_longitud: Optional[float] = None
    guardar_plantilla: bool = False

class RutaAsignar(BaseModel):
    chofer_id: uuid.UUID

class RutaUpdate(BaseModel):
    nombre: Optional[str] = None
    origen_descripcion: Optional[str] = None

class RutaResponse(BaseModel):
    id: str
    nombre: str
    estado: EstadoRuta
    total_km: Optional[float]
    tiempo_estimado_min: Optional[int]
    es_plantilla: bool
    origen_descripcion: Optional[str]
    chofer_id: Optional[str]
    creada_en: datetime
    iniciada_en: Optional[datetime]
    finalizada_en: Optional[datetime]
    paradas: List[ParadaResponse] = []

    class Config:
        from_attributes = True

class RutaListResponse(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    rutas: List[RutaResponse]