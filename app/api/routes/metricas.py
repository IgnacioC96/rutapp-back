# -*- coding: utf-8 -*-
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_admin
from app.db.database import get_db
from app.services import metricas

router = APIRouter(prefix="/metricas", tags=["Métricas"])


class NavegacionIn(BaseModel):
    url: str = Field(..., min_length=1, max_length=300, description="Ruta de la pantalla, ej: /admin/rutas/nueva")
    url_anterior: Optional[str] = Field(None, max_length=300)


@router.post("/navegacion", status_code=status.HTTP_204_NO_CONTENT)
def registrar_navegacion(
    datos: NavegacionIn,
    user_agent: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """El front avisa cada vez que el usuario cambia de pantalla. Las URL se normalizan (ids -> :id)."""
    metricas.registrar_navegacion(db, current_user.get("sub"), current_user.get("sid"),
                                  datos.url, datos.url_anterior, user_agent)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sesion/cerrar", status_code=status.HTTP_204_NO_CONTENT)
def cerrar_sesion(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Marca el fin de la sesión (botón Salir). Sirve para medir cuánto duran las sesiones."""
    metricas.cerrar_sesion(db, current_user.get("sub"), current_user.get("sid"), current_user.get("rol"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/dashboard")
def dashboard(
    desde: Optional[date] = Query(None, description="Primer día (inclusive). Por defecto: hace 30 días"),
    hasta: Optional[date] = Query(None, description="Último día (inclusive). Por defecto: hoy"),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Todos los indicadores del tablero de métricas. Solo administradores."""
    return metricas.tablero(db, desde, hasta)
