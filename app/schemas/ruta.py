# -*- coding: utf-8 -*-
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
    entrega_id: uuid.UUID
    cliente: str
    direccion: str
    tiempo_desde_anterior_min: Optional[int] = None
    distancia_desde_anterior_km: Optional[float] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_parada(cls, parada):
        """
        Construye el response de una parada resolviendo
        el nombre del cliente y la direccion desde las relaciones.
        """
        return cls(
            orden=parada.orden,
            entrega_id=parada.entrega_id,
            cliente=parada.entrega.cliente.nombre,
            direccion=parada.entrega.direccion.descripcion,
            tiempo_desde_anterior_min=parada.tiempo_desde_anterior_min,
            distancia_desde_anterior_km=parada.distancia_desde_anterior_km,
        )

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
    id: uuid.UUID
    nombre: str
    estado: EstadoRuta
    total_km: Optional[float] = None
    tiempo_estimado_min: Optional[int] = None
    es_plantilla: bool
    origen_descripcion: Optional[str] = None
    chofer_id: Optional[uuid.UUID] = None
    creada_en: datetime
    iniciada_en: Optional[datetime] = None
    finalizada_en: Optional[datetime] = None
    paradas: List[ParadaResponse] = []

    class Config:
        from_attributes = True

    @classmethod
    def from_ruta(cls, ruta):
        """
        Construye el response de una ruta convirtiendo
        cada parada con su cliente y direccion resueltos.
        """
        return cls(
            id=ruta.id,
            nombre=ruta.nombre,
            estado=ruta.estado,
            total_km=ruta.total_km,
            tiempo_estimado_min=ruta.tiempo_estimado_min,
            es_plantilla=ruta.es_plantilla,
            origen_descripcion=ruta.origen_descripcion,
            chofer_id=ruta.chofer_id,
            creada_en=ruta.creada_en,
            iniciada_en=ruta.iniciada_en,
            finalizada_en=ruta.finalizada_en,
            paradas=[ParadaResponse.from_parada(p) for p in ruta.paradas]
        )

class RutaListResponse(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    rutas: List[RutaResponse]