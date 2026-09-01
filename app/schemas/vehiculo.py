# -*- coding: utf-8 -*-
"""
Schemas Pydantic para la gestión de flota de vehículos.
Define los contratos de entrada y salida de la API para el módulo de flota.
"""
from pydantic import BaseModel, field_validator
from typing import Optional
from enum import Enum
import uuid


class EstadoVehiculo(str, Enum):
    """Estados operativos posibles de un vehículo."""
    disponible = "disponible"
    en_ruta = "en_ruta"
    mantenimiento = "mantenimiento"


class VehiculoCreate(BaseModel):
    """
    Body para POST /vehiculos — dar de alta un vehículo nuevo.
    La patente debe ser única en el sistema.
    """
    patente: str
    marca_modelo: str
    capacidad_kg: float
    # El chofer es opcional al crear — se puede asignar después
    chofer_id: Optional[uuid.UUID] = None

    @field_validator("patente")
    @classmethod
    def validar_patente(cls, v):
        # Normalizar a mayúsculas y verificar longitud mínima
        v = v.strip().upper()
        if len(v) < 6:
            raise ValueError("La patente debe tener al menos 6 caracteres")
        return v

    @field_validator("capacidad_kg")
    @classmethod
    def validar_capacidad(cls, v):
        if v <= 0:
            raise ValueError("La capacidad debe ser mayor a 0 kg")
        return v


class VehiculoUpdate(BaseModel):
    """
    Body para PUT /vehiculos/{id} — edición parcial de un vehículo.
    Todos los campos son opcionales — solo se actualizan los que vienen.
    """
    marca_modelo: Optional[str] = None
    capacidad_kg: Optional[float] = None
    estado: Optional[EstadoVehiculo] = None
    # Permite reasignar o desasignar el chofer (None = sin chofer)
    chofer_id: Optional[uuid.UUID] = None


class VehiculoResponse(BaseModel):
    """
    Respuesta de la API para un vehículo.
    Incluye el nombre del chofer asignado si lo tiene.
    """
    id: uuid.UUID
    patente: str
    marca_modelo: str
    capacidad_kg: float
    estado: EstadoVehiculo
    chofer_id: Optional[uuid.UUID] = None
    # Nombre del chofer denormalizado para evitar joins en el front
    chofer_nombre: Optional[str] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_vehiculo(cls, vehiculo):
        """
        Construye el response resolviendo el nombre del chofer
        desde la relación ORM si está asignado.
        """
        return cls(
            id=vehiculo.id,
            patente=vehiculo.patente,
            marca_modelo=vehiculo.marca_modelo,
            capacidad_kg=vehiculo.capacidad_kg,
            estado=vehiculo.estado,
            chofer_id=vehiculo.chofer_id,
            chofer_nombre=vehiculo.chofer.nombre if vehiculo.chofer else None,
        )


class VehiculoListResponse(BaseModel):
    """Respuesta paginada de GET /vehiculos."""
    total: int
    vehiculos: list[VehiculoResponse]