import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.database import Base

class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(150), nullable=False)
    telefono_whatsapp = Column(String(20), nullable=False)
    cuit = Column(String(15), nullable=True)
    notas = Column(Text, nullable=True)
    activo = Column(Boolean, default=True)

    direcciones = relationship(
        "DireccionCliente",
        back_populates="cliente",
        cascade="all, delete-orphan"
    )
    entregas = relationship("Entrega", back_populates="cliente")


class DireccionCliente(Base):
    __tablename__ = "direcciones_cliente"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False)
    descripcion = Column(String(255), nullable=False)
    referencia = Column(String(255), nullable=True)
    es_principal = Column(Boolean, default=False)

    cliente = relationship("Cliente", back_populates="direcciones")
    entregas = relationship("Entrega", back_populates="direccion")
