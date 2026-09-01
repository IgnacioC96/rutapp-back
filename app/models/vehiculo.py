# -*- coding: utf-8 -*-
"""
Modelo de Vehículo para la gestión de flota de RutApp.
Representa tanto vehículos propios como tercerizados asignados a choferes.
"""
import uuid
import enum
from sqlalchemy import Column, String, Float, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.database import Base


class EstadoVehiculo(enum.Enum):
    """
    Estados operativos posibles de un vehículo:
    - disponible: listo para ser asignado a una ruta
    - en_ruta: actualmente en servicio con un chofer
    - mantenimiento: fuera de servicio temporalmente
    """
    disponible = "disponible"
    en_ruta = "en_ruta"
    mantenimiento = "mantenimiento"


class Vehiculo(Base):
    """
    Tabla 'vehiculos' — registra la flota disponible para el sistema de reparto.
    Un vehículo puede estar asignado a un chofer o sin asignar.
    La relación con chofer es opcional: un vehículo puede existir sin chofer asignado,
    y un chofer puede no tener vehículo propio en el sistema.
    """
    __tablename__ = "vehiculos"

    # Identificador único universal — consistente con el resto del modelo de datos
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Patente del vehículo — debe ser única en el sistema
    patente = Column(String(10), unique=True, nullable=False)

    # Marca y modelo del vehículo (ej: "Ford Transit 2022")
    marca_modelo = Column(String(100), nullable=False)

    # Capacidad máxima de carga en kilogramos
    # Se usa para validar si el vehículo puede llevar el peso total de las entregas
    capacidad_kg = Column(Float, nullable=False)

    # Estado operativo actual del vehículo
    # Por defecto 'disponible' al ser dado de alta
    estado = Column(
        Enum(EstadoVehiculo),
        default=EstadoVehiculo.disponible,
        nullable=False
    )

    # FK al chofer asignado — nullable porque puede estar sin asignar
    chofer_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)

    # Relación ORM con el modelo Usuario
    # backref="vehiculo" permite acceder al vehículo desde el usuario: usuario.vehiculo
    chofer = relationship("Usuario", backref="vehiculo")