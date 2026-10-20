# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field, field_validator, model_validator
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
    # ID de la parada — necesario para reordenar con drag & drop
    id: uuid.UUID
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
                id=parada.id,
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
            id=parada.id,
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

class RetornoTipo(str, Enum):
    """A dónde vuelve el camión al terminar las entregas."""
    origen = "origen"      # vuelve al punto de salida
    otro = "otro"          # vuelve a otra dirección (se elige o se escribe)
    ninguno = "ninguno"    # no vuelve: la ruta termina en la última entrega


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
    # Retorno al terminar: por defecto 'ninguno' (comportamiento de siempre)
    retorno_tipo: RetornoTipo = RetornoTipo.ninguno
    retorno_descripcion: Optional[str] = None   # solo para retorno_tipo = 'otro'
    retorno_latitud: Optional[float] = Field(None, ge=-90, le=90)
    retorno_longitud: Optional[float] = Field(None, ge=-180, le=180)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre de la ruta no puede estar vacío")
        return v

    @field_validator("retorno_descripcion")
    @classmethod
    def _retorno_desc(cls, v):
        return (v.strip() or None) if v is not None else None

    @model_validator(mode="after")
    def _validar_retorno(self):
        if self.retorno_tipo == RetornoTipo.otro:
            tiene_coords = self.retorno_latitud is not None and self.retorno_longitud is not None
            if (self.retorno_latitud is None) != (self.retorno_longitud is None):
                raise ValueError("Mandá latitud y longitud de retorno juntas, o ninguna de las dos")
            if not tiene_coords and not self.retorno_descripcion:
                raise ValueError("Para volver a otra dirección indicá la dirección o sus coordenadas")
        return self

class RutaAsignar(BaseModel):
    """Body para PATCH /rutas/{id}/asignar."""
    chofer_id: uuid.UUID

class RutaUpdate(BaseModel):
    """Body para PATCH /rutas/{id} — edición parcial de metadatos."""
    nombre: Optional[str] = None
    origen_descripcion: Optional[str] = None

def entregas_pendientes(ruta) -> int:
    """Paradas de entrega sin confirmar (las paradas extra no cuentan)."""
    return sum(1 for p in ruta.paradas if not p.completada and not p.es_parada_extra)


def fase_ruta(ruta) -> Optional[str]:
    """'entregas' | 'regreso' | None (si la ruta no está en curso)."""
    # El estado del modelo es otro Enum que el de este schema: se compara por valor
    if getattr(ruta.estado, "value", ruta.estado) != EstadoRuta.en_curso.value:
        return None
    if entregas_pendientes(ruta) == 0 and (ruta.retorno_tipo or "ninguno") != "ninguno":
        return "regreso"
    return "entregas"


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
    # Retorno al terminar las entregas
    retorno_tipo: str = "ninguno"
    retorno_descripcion: Optional[str] = None
    retorno_latitud: Optional[float] = None
    retorno_longitud: Optional[float] = None
    retorno_km: Optional[float] = None
    retorno_min: Optional[int] = None
    # "entregas" mientras quedan entregas por confirmar, "regreso" cuando ya se
    # entregó todo y falta volver; null si la ruta no está en curso
    fase: Optional[str] = None
    # Última ubicación GPS del chofer
    chofer_latitud: Optional[float] = None
    chofer_longitud: Optional[float] = None
    ubicacion_actualizada_en: Optional[datetime] = None
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
            retorno_tipo=ruta.retorno_tipo or "ninguno",
            retorno_descripcion=ruta.retorno_descripcion,
            retorno_latitud=ruta.retorno_latitud,
            retorno_longitud=ruta.retorno_longitud,
            retorno_km=ruta.retorno_km,
            retorno_min=ruta.retorno_min,
            fase=fase_ruta(ruta),
            chofer_latitud=ruta.chofer_latitud,
            chofer_longitud=ruta.chofer_longitud,
            ubicacion_actualizada_en=ruta.ubicacion_actualizada_en,
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
    # Ubicación actual del chofer — se actualiza cada 15 segundos
    chofer_latitud: Optional[float] = None
    chofer_longitud: Optional[float] = None
    # Fase del recorrido y punto de retorno, para mostrar "volviendo a ..." al cliente/admin
    fase: Optional[str] = None
    retorno_descripcion: Optional[str] = None
    retorno_latitud: Optional[float] = None
    retorno_longitud: Optional[float] = None

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
    descripcion: str = Field(..., max_length=200)   # ej: "Carga de nafta YPF Morón"
    direccion: Optional[str] = Field(None, max_length=255)  # dirección opcional de la parada
    orden: Optional[int] = Field(None, ge=1)        # posición deseada (al final si no se especifica)
    latitud: Optional[float] = Field(None, ge=-90, le=90)   # coordenadas opcionales para el mapa
    longitud: Optional[float] = Field(None, ge=-180, le=180)

    @field_validator("descripcion")
    @classmethod
    def _descripcion(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La descripción de la parada no puede estar vacía")
        return v

    @field_validator("direccion")
    @classmethod
    def _direccion(cls, v):
        return (v.strip() or None) if v is not None else None

    @model_validator(mode="after")
    def _coordenadas_juntas(self):
        if (self.latitud is None) != (self.longitud is None):
            raise ValueError("Mandá latitud y longitud juntas, o ninguna de las dos")
        return self


class ParadaExtraUpdate(BaseModel):
    """Body para PATCH /rutas/{id}/paradas/{parada_id} — editar una parada extra.
    Todos los campos son opcionales; solo se cambian los que se mandan.
    Para quitar la dirección o las coordenadas, mandalas en null."""
    descripcion: Optional[str] = Field(None, max_length=200)
    direccion: Optional[str] = Field(None, max_length=255)
    latitud: Optional[float] = Field(None, ge=-90, le=90)
    longitud: Optional[float] = Field(None, ge=-180, le=180)

    @field_validator("descripcion")
    @classmethod
    def _descripcion(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("La descripción de la parada no puede estar vacía")
        return v

    @field_validator("direccion")
    @classmethod
    def _direccion(cls, v):
        return (v.strip() or None) if v is not None else None