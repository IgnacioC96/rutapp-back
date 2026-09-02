# -*- coding: utf-8 -*-
"""
Modelos de Ruta y ParadaRuta para RutApp.
Una ruta agrupa un conjunto de paradas ordenadas por el algoritmo Nearest Neighbor.
Las paradas pueden ser entregas a clientes o paradas extra (nafta, comida, etc.).
"""
import uuid
import enum
import secrets
from sqlalchemy import Column, String, Boolean, ForeignKey, Float, Integer, DateTime, Enum, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


class EstadoRuta(enum.Enum):
    """
    Ciclo de vida de una ruta:
    pendiente → asignada → en_curso → completada / finalizada
    'finalizada' es el estado de emergencia cuando quedan entregas sin confirmar.
    """
    pendiente = "pendiente"
    asignada = "asignada"
    en_curso = "en_curso"
    completada = "completada"
    finalizada = "finalizada"


class Ruta(Base):
    """
    Tabla 'rutas' — representa un recorrido de entregas optimizado.
    Puede ser una ruta operativa o una plantilla reutilizable (es_plantilla=True).
    """
    __tablename__ = "rutas"

    # Identificador único universal
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Nombre descriptivo de la ruta (ej: "Ruta del lunes zona norte")
    nombre = Column(String(100), nullable=False)

    # Punto de origen del recorrido — puede venir como texto o coordenadas
    origen_descripcion = Column(String(255), nullable=True)
    origen_latitud = Column(Float, nullable=True)
    origen_longitud = Column(Float, nullable=True)

    # Chofer asignado — nullable hasta que el admin lo asigne
    chofer_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)

    # Estado operativo de la ruta
    estado = Column(Enum(EstadoRuta), default=EstadoRuta.pendiente)

    # Métricas calculadas por el algoritmo de optimización
    total_km = Column(Float, nullable=True)
    tiempo_estimado_min = Column(Integer, nullable=True)

    # Si es True, esta ruta es una plantilla reutilizable (no una ruta operativa)
    es_plantilla = Column(Boolean, default=False)

    # Sprint 3 — fecha operativa para la que se planificó la ruta
    fecha_programada = Column(Date, nullable=True)

    # Sprint 3 — código único para el seguimiento público sin autenticación
    codigo_seguimiento = Column(String(12), unique=True, nullable=True,
                                default=lambda: secrets.token_urlsafe(8))

    # Timestamps del ciclo de vida
    creada_en = Column(DateTime(timezone=True), server_default=func.now())
    iniciada_en = Column(DateTime(timezone=True), nullable=True)
    finalizada_en = Column(DateTime(timezone=True), nullable=True)

    # Relaciones ORM
    chofer = relationship("Usuario", back_populates="rutas")
    entregas = relationship("Entrega", back_populates="ruta")
    paradas = relationship(
        "ParadaRuta",
        back_populates="ruta",
        order_by="ParadaRuta.orden"
    )


class ParadaRuta(Base):
    """
    Tabla 'paradas_ruta' — cada fila es una parada dentro de una ruta.

    Tipos de parada:
    - Parada de entrega: entrega_id no es null, es_parada_extra=False
    - Parada extra: entrega_id es null, es_parada_extra=True
      (ej: carga de nafta, almuerzo, parada técnica)

    El orden define la secuencia optimizada generada por Nearest Neighbor,
    pero el admin puede modificarlo manualmente después de crear la ruta.
    """
    __tablename__ = "paradas_ruta"

    # Identificador único universal
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK a la ruta a la que pertenece esta parada
    ruta_id = Column(UUID(as_uuid=True), ForeignKey("rutas.id"), nullable=False)

    # FK a la entrega — nullable para paradas extra que no son entregas a clientes
    entrega_id = Column(UUID(as_uuid=True), ForeignKey("entregas.id"), nullable=True)

    # Posición de la parada en el recorrido (1 = primera, 2 = segunda, etc.)
    orden = Column(Integer, nullable=False)

    # Métricas de distancia respecto a la parada anterior
    tiempo_desde_anterior_min = Column(Integer, nullable=True)
    distancia_desde_anterior_km = Column(Float, nullable=True)

    # Sprint 3 — estado de confirmación por QR o código manual
    completada = Column(Boolean, default=False)

    # Sprint 3 — coordenadas geocodificadas para el mapa
    latitud = Column(Float, nullable=True)
    longitud = Column(Float, nullable=True)

    # Sprint 3 — campos para paradas extra (nafta, comida, parada técnica, etc.)
    # Solo se usan cuando entrega_id es null
    es_parada_extra = Column(Boolean, default=False)
    descripcion_extra = Column(String(200), nullable=True)  # ej: "Carga de nafta YPF"
    direccion_extra = Column(String(255), nullable=True)    # dirección de la parada extra

    # Relaciones ORM
    ruta = relationship("Ruta", back_populates="paradas")
    # nullable=True porque las paradas extra no tienen entrega asociada
    entrega = relationship("Entrega")