# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
import uuid
from app.core.geo import coordenadas_validas


def _limpiar(v: Optional[str]) -> Optional[str]:
    return v.strip() if isinstance(v, str) else v


class PuntoSalidaCreate(BaseModel):
    """Alta de un punto de salida. Si no se mandan coordenadas, el backend ubica la dirección en el mapa."""
    nombre: str = Field(..., max_length=100)
    descripcion: str = Field(..., max_length=255)
    latitud: Optional[float] = Field(None, ge=-90, le=90)
    longitud: Optional[float] = Field(None, ge=-180, le=180)
    es_predeterminado: bool = False

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v

    @field_validator("descripcion")
    @classmethod
    def _descripcion(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La dirección no puede estar vacía")
        return v

    @model_validator(mode="after")
    def _coords_juntas(self):
        coordenadas_validas(self.latitud, self.longitud)
        return self


class PuntoSalidaUpdate(BaseModel):
    """Edición parcial. Si cambia la dirección y no se mandan coordenadas nuevas, se vuelve a ubicar en el mapa."""
    nombre: Optional[str] = Field(None, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    latitud: Optional[float] = Field(None, ge=-90, le=90)
    longitud: Optional[float] = Field(None, ge=-180, le=180)

    @field_validator("nombre", "descripcion")
    @classmethod
    def _no_vacio(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("No puede estar vacío")
        return v

    @model_validator(mode="after")
    def _coords_juntas(self):
        coordenadas_validas(self.latitud, self.longitud)
        return self


class PuntoSalidaResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    descripcion: str
    latitud: float
    longitud: float
    es_predeterminado: bool
    activo: bool
    creado_en: Optional[datetime] = None

    class Config:
        from_attributes = True


class PuntoSalidaListResponse(BaseModel):
    total: int
    puntos: List[PuntoSalidaResponse]
