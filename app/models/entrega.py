import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, Text, Float, Integer, Date, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import enum

class EstadoEntrega(enum.Enum):
    pendiente = "pendiente"
    en_curso = "en_curso"
    completada = "completada"
    cancelada = "cancelada"

class Entrega(Base):
    __tablename__ = "entregas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False)
    direccion_id = Column(UUID(as_uuid=True), ForeignKey("direcciones_cliente.id"), nullable=False)
    ruta_id = Column(UUID(as_uuid=True), ForeignKey("rutas.id"), nullable=True)

    descripcion = Column(String(255), nullable=False)
    bultos = Column(Integer, default=1)
    peso_kg = Column(Float, nullable=True)
    fecha_estimada = Column(Date, nullable=True)
    observaciones = Column(Text, nullable=True)
    observaciones_chofer = Column(Text, nullable=True)

    estado = Column(Enum(EstadoEntrega), default=EstadoEntrega.pendiente)

    creada_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizada_en = Column(DateTime(timezone=True), onupdate=func.now())

    cliente = relationship("Cliente", back_populates="entregas")
    direccion = relationship("DireccionCliente", back_populates="entregas")
    ruta = relationship("Ruta", back_populates="entregas")
