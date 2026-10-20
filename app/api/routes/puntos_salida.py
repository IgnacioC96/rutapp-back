# -*- coding: utf-8 -*-
"""
Puntos de salida guardados (depósito, box, sucursal). Solo admin.
Se usan al armar una ruta como origen (origen_punto_id) o como punto de retorno
(retorno_punto_id). Ver POST /rutas.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
import uuid
from app.db.database import get_db
from app.models.punto_salida import PuntoSalida
from app.schemas.punto_salida import (
    PuntoSalidaCreate, PuntoSalidaUpdate, PuntoSalidaResponse, PuntoSalidaListResponse
)
from app.core.security import require_admin
from app.services.optimizacion import geocodificar_direccion, ServicioMapasError
from app.core.exceptions import logger

router = APIRouter(prefix="/puntos-salida", tags=["Puntos de salida"])


def _obtener_o_404(db: Session, punto_id: uuid.UUID) -> PuntoSalida:
    punto = db.query(PuntoSalida).filter(PuntoSalida.id == punto_id, PuntoSalida.activo.is_(True)).first()
    if not punto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Punto de salida no encontrado")
    return punto


def _nombre_duplicado(db: Session, nombre: str, excluir: uuid.UUID | None = None) -> bool:
    q = db.query(PuntoSalida).filter(
        func.lower(PuntoSalida.nombre) == nombre.lower(), PuntoSalida.activo.is_(True)
    )
    if excluir:
        q = q.filter(PuntoSalida.id != excluir)
    return db.query(q.exists()).scalar()


async def _ubicar(descripcion: str) -> tuple[float, float]:
    """Devuelve (latitud, longitud) de una dirección, o levanta un error claro."""
    try:
        coords = await geocodificar_direccion(descripcion)
    except ServicioMapasError as exc:
        logger.error(f"Servicio de mapas no disponible al ubicar punto de salida: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo ubicar la dirección porque el servicio de mapas no respondió. Probá de nuevo en unos minutos"
        )
    if not coords:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo ubicar la dirección en el mapa. Revisala o marcá el punto en el mapa (latitud y longitud)"
        )
    return coords[1], coords[0]   # ORS devuelve (longitud, latitud)


@router.get("", response_model=PuntoSalidaListResponse)
def listar_puntos(
    incluir_inactivos: bool = Query(False, description="Incluye los dados de baja"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Lista los puntos de salida activos (el predeterminado primero, después por nombre)."""
    q = db.query(PuntoSalida)
    if not incluir_inactivos:
        q = q.filter(PuntoSalida.activo.is_(True))
    puntos = q.order_by(PuntoSalida.es_predeterminado.desc(), func.lower(PuntoSalida.nombre)).all()
    return PuntoSalidaListResponse(total=len(puntos), puntos=puntos)


@router.post("", response_model=PuntoSalidaResponse, status_code=201)
async def crear_punto(
    datos: PuntoSalidaCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Crea un punto de salida. Si no se mandan latitud/longitud, se ubica la dirección en el mapa.
    El nombre no se puede repetir entre los puntos activos. Si es_predeterminado es true,
    deja de serlo el anterior.
    """
    if _nombre_duplicado(db, datos.nombre):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un punto de salida con ese nombre")

    lat, lon = datos.latitud, datos.longitud
    if lat is None:
        lat, lon = await _ubicar(datos.descripcion)

    # Si todavía no hay ninguno, el primero queda como predeterminado
    hay_activos = db.query(PuntoSalida).filter(PuntoSalida.activo.is_(True)).count() > 0
    predeterminado = datos.es_predeterminado or not hay_activos
    if predeterminado:
        db.query(PuntoSalida).update({PuntoSalida.es_predeterminado: False})

    punto = PuntoSalida(
        nombre=datos.nombre, descripcion=datos.descripcion,
        latitud=lat, longitud=lon, es_predeterminado=predeterminado
    )
    db.add(punto)
    db.commit()
    db.refresh(punto)
    return punto


@router.put("/{punto_id}", response_model=PuntoSalidaResponse)
async def editar_punto(
    punto_id: uuid.UUID,
    datos: PuntoSalidaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Edita nombre, dirección o coordenadas. Si cambia la dirección y no se mandan coordenadas,
    se vuelve a ubicar en el mapa. Las rutas ya armadas no se modifican.
    """
    punto = _obtener_o_404(db, punto_id)
    campos = datos.model_fields_set

    if "nombre" in campos and datos.nombre is not None:
        if _nombre_duplicado(db, datos.nombre, excluir=punto.id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un punto de salida con ese nombre")
        punto.nombre = datos.nombre

    if datos.latitud is not None:
        punto.latitud, punto.longitud = datos.latitud, datos.longitud
        if datos.descripcion is not None:
            punto.descripcion = datos.descripcion
    elif datos.descripcion is not None and datos.descripcion != punto.descripcion:
        punto.latitud, punto.longitud = await _ubicar(datos.descripcion)
        punto.descripcion = datos.descripcion

    db.commit()
    db.refresh(punto)
    return punto


@router.patch("/{punto_id}/predeterminado", response_model=PuntoSalidaResponse)
def marcar_predeterminado(
    punto_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Marca este punto como el predeterminado (el que el front preselecciona). Solo uno a la vez."""
    punto = _obtener_o_404(db, punto_id)
    db.query(PuntoSalida).update({PuntoSalida.es_predeterminado: False})
    punto.es_predeterminado = True
    db.commit()
    db.refresh(punto)
    return punto


@router.delete("/{punto_id}", status_code=204)
def dar_de_baja_punto(
    punto_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Baja lógica. Las rutas ya armadas con este punto no cambian (guardan su propia copia).
    Si era el predeterminado, el más antiguo de los activos pasa a serlo.
    """
    punto = _obtener_o_404(db, punto_id)
    era_predeterminado = punto.es_predeterminado
    punto.activo = False
    punto.es_predeterminado = False
    db.flush()
    if era_predeterminado:
        siguiente = db.query(PuntoSalida).filter(PuntoSalida.activo.is_(True)).order_by(PuntoSalida.creado_en).first()
        if siguiente:
            siguiente.es_predeterminado = True
    db.commit()
