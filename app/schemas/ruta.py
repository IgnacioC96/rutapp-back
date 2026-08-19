# -*- coding: utf-8 -*-
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
import uuid

class EstadoRuta(str, Enum):
    pendiente = "pendiente"
    asignada = "asignada"
    en_curso = "en_curso"
    completada = "completada"
    finalizada = "finalizada"

class ParadaResponse(BaseModel):
    """
    Representa una parada dentro de una ruta optimizada.
    Incluye datos denormalizados del cliente y dirección para
    evitar joins adicionales en el frontend.
    """
    orden: int
    entrega_id: uuid.UUID
    cliente: str
    direccion: str
    tiempo_desde_anterior_min: Optional[int] = None
    distancia_desde_anterior_km: Optional[float] = None
    # Sprint 3 — estado de confirmación y coordenadas para el mapa
    completada: bool = False
    latitud: Optional[float] = None
    longitud: Optional[float] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_parada(cls, parada):
        """
        Construye el response de una parada resolviendo
        el nombre del cliente y la dirección desde las relaciones ORM.
        """
        return cls(
            orden=parada.orden,
            entrega_id=parada.entrega_id,
            cliente=parada.entrega.cliente.nombre,
            direccion=parada.entrega.direccion.descripcion,
            tiempo_desde_anterior_min=parada.tiempo_desde_anterior_min,
            distancia_desde_anterior_km=parada.distancia_desde_anterior_km,
            completada=parada.completada or False,
            latitud=parada.latitud,
            longitud=parada.longitud,
        )

class RutaCreate(BaseModel):
    """
    Body para POST /rutas.
    El back geocodifica las direcciones, calcula la matriz de distancias
    y aplica Nearest Neighbor para ordenar las paradas automáticamente.
    """
    nombre: str
    entregas_ids: List[uuid.UUID]
    origen_descripcion: Optional[str] = None
    origen_latitud: Optional[float] = None
    origen_longitud: Optional[float] = None
    guardar_plantilla: bool = False
    # Sprint 3 — fecha operativa para la que se planifica la ruta
    fecha_programada: Optional[date] = None

class RutaAsignar(BaseModel):
    """Body para PATCH /rutas/{id}/asignar."""
    chofer_id: uuid.UUID

class RutaUpdate(BaseModel):
    """Body para PATCH /rutas/{id} — edición parcial de metadatos."""
    nombre: Optional[str] = None
    origen_descripcion: Optional[str] = None

class RutaResponse(BaseModel):
    """
    Respuesta completa de una ruta con sus paradas ordenadas.
    Usado en GET /rutas/{id}, POST /rutas y todos los PATCH de estado.
    """
    id: uuid.UUID
    nombre: str
    estado: EstadoRuta
    total_km: Optional[float] = None
    tiempo_estimado_min: Optional[int] = None
    es_plantilla: bool
    # Sprint 3 — fecha operativa y código de seguimiento público
    fecha_programada: Optional[date] = None
    codigo_seguimiento: Optional[str] = None
    origen_descripcion: Optional[str] = None
    origen_latitud: Optional[float] = None
    origen_longitud: Optional[float] = None
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
        Construye el response completo de una ruta convirtiendo
        cada parada con su cliente y dirección resueltos desde ORM.
        """
        return cls(
            id=ruta.id,
            nombre=ruta.nombre,
            estado=ruta.estado,
            total_km=ruta.total_km,
            tiempo_estimado_min=ruta.tiempo_estimado_min,
            es_plantilla=ruta.es_plantilla,
            fecha_programada=ruta.fecha_programada,
            codigo_seguimiento=ruta.codigo_seguimiento,
            origen_descripcion=ruta.origen_descripcion,
            origen_latitud=ruta.origen_latitud,
            origen_longitud=ruta.origen_longitud,
            chofer_id=ruta.chofer_id,
            creada_en=ruta.creada_en,
            iniciada_en=ruta.iniciada_en,
            finalizada_en=ruta.finalizada_en,
            paradas=[ParadaResponse.from_parada(p) for p in ruta.paradas]
        )

class RutaListResponse(BaseModel):
    """Respuesta paginada de GET /rutas."""
    total: int
    pagina: int
    por_pagina: int
    rutas: List[RutaResponse]


# ── Sprint 3: schemas nuevos ──────────────────────────────────────────────────

class ConfirmarEntregaRequest(BaseModel):
    """
    Body para PATCH /rutas/{id}/entregas/{entrega_id}/confirmar.
    El chofer ingresa el código QR o manual para confirmar la entrega.
    """
    codigo: str

class UbicacionRequest(BaseModel):
    """
    Body para PATCH /rutas/{id}/ubicacion.
    El chofer reporta su posición GPS cada 15 segundos desde el front.
    """
    latitud: float
    longitud: float

class SeguimientoParadaResponse(BaseModel):
    """Datos mínimos de una parada para la vista pública de seguimiento."""
    orden: int
    cliente: str
    direccion: str
    completada: bool

class SeguimientoResponse(BaseModel):
    """
    Respuesta de GET /seguimiento/{codigo}.
    Vista pública accesible sin autenticación — el cliente
    puede ver el progreso de su entrega en tiempo real.
    """
    codigo: str
    ruta_nombre: str
    estado: EstadoRuta
    chofer_nombre: str
    # Porcentaje de paradas completadas (0-100)
    progreso: int
    proxima_parada: Optional[SeguimientoParadaResponse] = None
    ultima_actualizacion: Optional[datetime] = None