# -*- coding: utf-8 -*-
"""
Modelos de Cliente y DireccionCliente para RutApp.
Un cliente puede tener hasta 3 direcciones, una de las cuales es la principal.
Las direcciones almacenan coordenadas geocodificadas para el mapa en el front.
"""
import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, Text, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.database import Base


class Cliente(Base):
    """
    Tabla 'clientes' — representa a los destinatarios de las entregas.
    Usa borrado lógico (activo=False) para mantener trazabilidad histórica.
    """
    __tablename__ = "clientes"

    # Identificador único universal
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Datos de contacto del cliente
    nombre = Column(String(150), nullable=False)
    telefono_whatsapp = Column(String(20), nullable=False)
    cuit = Column(String(15), nullable=True)
    notas = Column(Text, nullable=True)

    # Borrado lógico — los clientes inactivos no aparecen en listados
    activo = Column(Boolean, default=True)

    # Relaciones ORM
    direcciones = relationship(
        "DireccionCliente",
        back_populates="cliente",
        cascade="all, delete-orphan"
    )
    entregas = relationship("Entrega", back_populates="cliente")


class DireccionCliente(Base):
    """
    Tabla 'direcciones_cliente' — cada cliente puede tener hasta 3 direcciones.
    Una debe ser marcada como principal (es_principal=True).

    Sprint 3: se agregan campos de coordenadas (latitud, longitud) para que
    el front muestre un mapa con pin arrastrable al cargar la dirección,
    permitiendo ajustar las coordenadas con mayor precisión antes de geocodificar.
    """
    __tablename__ = "direcciones_cliente"

    # Identificador único universal
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK al cliente propietario de esta dirección
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False)

    # Descripción textual de la dirección (ej: "Av. Corrientes 1234, CABA")
    descripcion = Column(String(255), nullable=False)

    # Referencia adicional para el chofer (ej: "Piso 3, timbre B")
    referencia = Column(String(255), nullable=True)

    # Indica si esta es la dirección principal del cliente
    es_principal = Column(Boolean, default=False)

    # Sprint 3 — coordenadas geocodificadas para el mapa en Alta Cliente
    # Se llenan cuando el admin fija el pin en el mapa o al geocodificar
    latitud = Column(Float, nullable=True)
    longitud = Column(Float, nullable=True)

    # Relaciones ORM
    cliente = relationship("Cliente", back_populates="direcciones")
    entregas = relationship("Entrega", back_populates="direccion")