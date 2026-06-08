import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, Float, Integer, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import enum

class EstadoRuta(enum.Enum):
    pendiente = "pendiente"
    asignada = "asignada"
    en_curso = "en_curso"
    completada = "completada"
    finalizada = "finalizada"

class Ruta(Base):
    __tablename__ = "rutas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(100), nullable=False)
    origen_descripcion = Column(String(255), nullable=True)
    origen_latitud = Column(Float, nullable=True)
    origen_longitud = Column(Float, nullable=True)
    chofer_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)

    estado = Column(Enum(EstadoRuta), default=EstadoRuta.pendiente)
    total_km = Column(Float, nullable=True)
    tiempo_estimado_min = Column(Integer, nullable=True)
    es_plantilla = Column(Boolean, default=False)

    creada_en = Column(DateTime(timezone=True), server_default=func.now())
    iniciada_en = Column(DateTime(timezone=True), nullable=True)
    finalizada_en = Column(DateTime(timezone=True), nullable=True)

    chofer = relationship("Usuario", back_populates="rutas")
    entregas = relationship("Entrega", back_populates="ruta")
    paradas = relationship(
        "ParadaRuta",
        back_populates="ruta",
        order_by="ParadaRuta.orden"
    )


class ParadaRuta(Base):
    __tablename__ = "paradas_ruta"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ruta_id = Column(UUID(as_uuid=True), ForeignKey("rutas.id"), nullable=False)
    entrega_id = Column(UUID(as_uuid=True), ForeignKey("entregas.id"), nullable=False)

    orden = Column(Integer, nullable=False)
    tiempo_desde_anterior_min = Column(Integer, nullable=True)
    distancia_desde_anterior_km = Column(Float, nullable=True)

    ruta = relationship("Ruta", back_populates="paradas")
    entrega = relationship("Entrega")
