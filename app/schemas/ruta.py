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
    Puede ser una entrega a cliente o una parada extra operativa.
    Incluye datos denormalizados del cliente y dirección para
    evitar joins adicionales en el frontend.
    """
    orden: int
    entrega_id: Optional[uuid.UUID] = None
    cliente: Optional[str] = None
    direccion: Optional[str] = None
    tiempo_desde_anterior_min: Optional[int] = None
    distancia_desde_anterior_km: Optional[float] = None
    # Sprint 3 — estado de confirmación y coordenadas para el mapa
    completada: bool = False
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    # Sprint 3 — campos para paradas extra
    es_parada_extra: bool = False
    descripcion_extra: Optional[str] = None
    direccion_extra: Optional[str] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_parada(cls, parada):
        """
        Construye el response de una parada.
        Si es parada extra, usa descripcion_extra y direccion_extra.
        Si es entrega normal, resuelve cliente y dirección desde ORM.
        """
        if parada.es_parada_extra:
            # Parada extra — no tiene entrega asociada
            return cls(
                orden=parada.orden,
                entrega_id=None,
                cliente=None,
                direccion=parada.direccion_extra,
                completada=parada.completada or False,
                latitud=parada.latitud,
                longitud=parada.longitud,
                es_parada_extra=True,
                descripcion_extra=parada.descripcion_extra,
                direccion_extra=parada.direccion_extra,
            )
        # Parada normal de entrega a cliente
        return cls(
            orden=parada.orden,
            entrega_id=parada.entrega_id,
            cliente=parada.entrega.cliente.nombre if parada.entrega else None,
            direccion=parada.entrega.direccion.descripcion if parada.entrega else None,
            tiempo_desde_anterior_min=parada.tiempo_desde_anterior_min,
            distancia_desde_anterior_km=parada.distancia_desde_anterior_km,
            completada=parada.completada or False,
            latitud=parada.latitud,
            longitud=parada.longitud,
            es_parada_extra=False,
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

    # ── Sprint 3: edición manual de rutas ─────────────────────────────────────────

class ParadaReordenarItem(BaseModel):
    """
    Item individual para reordenar paradas.
    El front manda la lista completa con el nuevo orden deseado.
    """
    # ID de la parada (no de la entrega)
    parada_id: uuid.UUID
    # Nuevo número de orden (1 = primera parada)
    orden: int


class ReordenarParadasRequest(BaseModel):
    """
    Body para PATCH /rutas/{id}/paradas — reordenar paradas manualmente.
    El admin arrastra las paradas en el front y manda el nuevo orden completo.
    """
    paradas: list[ParadaReordenarItem]


class ParadaExtraCreate(BaseModel):
    """
    Body para POST /rutas/{id}/paradas/extra — agregar parada extra.
    Las paradas extra no son entregas a clientes — son paradas operativas
    como carga de nafta, almuerzo, parada técnica, etc.
    """
    descripcion: str                    # ej: "Carga de nafta YPF Morón"
    direccion: Optional[str] = None     # dirección opcional de la parada
    orden: Optional[int] = None         # posición deseada (al final si no se especifica)
    latitud: Optional[float] = None     # coordenadas opcionales para el mapa
    longitud: Optional[float] = None