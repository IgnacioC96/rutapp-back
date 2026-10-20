# -*- coding: utf-8 -*-
"""
Modelo de Punto de salida: lugares guardados (depósito, box, sucursal) que el admin
elige al armar una ruta, como origen o como punto de retorno.
La ruta guarda una COPIA de la dirección y las coordenadas: si después se edita
o se da de baja el punto, las rutas ya armadas no cambian.
"""
import uuid
from sqlalchemy import Column, String, Float, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.database import Base


class PuntoSalida(Base):
    __tablename__ = "puntos_salida"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(100), nullable=False)             # ej: "Depósito Morón"
    descripcion = Column(String(255), nullable=False)        # dirección en texto
    latitud = Column(Float, nullable=False)
    longitud = Column(Float, nullable=False)
    # Si es True, el front lo preselecciona al armar una ruta (solo uno a la vez)
    es_predeterminado = Column(Boolean, nullable=False, default=False, server_default="false")
    activo = Column(Boolean, nullable=False, default=True, server_default="true")
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
