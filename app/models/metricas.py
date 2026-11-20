# -*- coding: utf-8 -*-
"""
Modelos de analítica de uso (métricas).

Tres tablas, pensadas para responder las preguntas del informe de métricas:
  - eventos_usuario  : bitácora de acciones (LOGIN, CREAR_ENTREGA, CONFIRMAR_ENTREGA, ...)
  - sesiones_usuario : una fila por inicio de sesión (duración, dispositivo, navegador)
  - navegacion       : una fila por pantalla visitada (qué URL, desde cuál, a qué hora)

Ninguna guarda datos personales sensibles: no se registran contraseñas, textos buscados
ni contenido de los formularios. La columna `simulado` marca los datos de prueba generados
por scripts/simular_metricas.py para poder borrarlos sin tocar los reales.
"""
import uuid
from sqlalchemy import Column, String, Boolean, Integer, SmallInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.database import Base


class SesionUsuario(Base):
    __tablename__ = "sesiones_usuario"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    rol = Column(String(10), nullable=True)
    fecha_inicio = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    # Se completa al cerrar sesión. Si el usuario no cierra, la sesión termina en ultima_actividad.
    fecha_fin = Column(DateTime(timezone=True), nullable=True)
    ultima_actividad = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    dispositivo = Column(String(15), nullable=True)      # escritorio | movil | tablet
    navegador = Column(String(30), nullable=True)
    sistema_operativo = Column(String(30), nullable=True)
    simulado = Column(Boolean, nullable=False, default=False, server_default="false")


class EventoUsuario(Base):
    __tablename__ = "eventos_usuario"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    sesion_id = Column(UUID(as_uuid=True), ForeignKey("sesiones_usuario.id", ondelete="SET NULL"), nullable=True)
    rol = Column(String(10), nullable=True)
    fecha = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    evento = Column(String(50), nullable=False, index=True)       # ej: CREAR_ENTREGA
    # sesion | crear | editar | eliminar | operacion | busqueda
    tipo = Column(String(15), nullable=False)
    entidad = Column(String(30), nullable=True)                   # cliente, entrega, ruta, ...
    entidad_id = Column(String(40), nullable=True)
    descripcion = Column(String(500), nullable=True)
    http_status = Column(SmallInteger, nullable=True)
    duracion_ms = Column(Integer, nullable=True)                  # tiempo de respuesta de la API
    simulado = Column(Boolean, nullable=False, default=False, server_default="false")


class Navegacion(Base):
    __tablename__ = "navegacion"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    sesion_id = Column(UUID(as_uuid=True), ForeignKey("sesiones_usuario.id", ondelete="SET NULL"), nullable=True)
    fecha = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    url = Column(String(300), nullable=False, index=True)         # normalizada: /admin/rutas/:id
    url_anterior = Column(String(300), nullable=True)             # para reconstruir el flujo
    dispositivo = Column(String(15), nullable=True)
    navegador = Column(String(30), nullable=True)
    simulado = Column(Boolean, nullable=False, default=False, server_default="false")
