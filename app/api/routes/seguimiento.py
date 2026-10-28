# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.ruta import Ruta, EstadoRuta
from app.schemas.ruta import SeguimientoResponse, SeguimientoParadaResponse, fase_ruta
from datetime import datetime, timezone, timedelta

# Router separado para evitar conflicto con /{ruta_id} en el router de rutas
router = APIRouter(prefix="/seguimiento", tags=["Seguimiento"])


@router.get("/{codigo}", response_model=SeguimientoResponse)
def seguimiento_publico(
    codigo: str,
    db: Session = Depends(get_db)
    # Sin autenticación — es una vista pública accesible por el cliente
):
    """
    Vista pública de seguimiento de una ruta por código.
    No requiere autenticación — el cliente accede con el código de su entrega.
    Devuelve progreso, próxima parada, nombre del chofer y última ubicación.
    """
    # Buscar la ruta por su código de seguimiento único
    ruta = db.query(Ruta).filter(Ruta.codigo_seguimiento == codigo).first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No encontramos este seguimiento"
        )

    # Calcular el progreso como porcentaje de paradas completadas
    # Las paradas extra (nafta, almuerzo) no cuentan para el progreso de las entregas
    paradas_entrega = [p for p in ruta.paradas if not p.es_parada_extra]
    total_paradas = len(paradas_entrega)
    # Una parada "no entregada" también está resuelta: el chofer ya siguió de largo
    paradas_completadas = sum(1 for p in paradas_entrega if p.completada or p.omitida)
    progreso = int((paradas_completadas / total_paradas) * 100) if total_paradas > 0 else 0

    # Determinar la próxima parada (la primera no completada en orden)
    proxima_parada = None
    for parada in paradas_entrega:
        if not parada.completada and not parada.omitida:
            proxima_parada = SeguimientoParadaResponse(
                orden=parada.orden,
                # Vista pública: no se expone el nombre ni la dirección del cliente
                cliente=f"Parada {paradas_entrega.index(parada) + 1} de {total_paradas}",
                direccion="",
                completada=parada.completada
            )
            break

    # Nombre del chofer asignado (o anónimo si no hay)
    chofer_nombre = ruta.chofer.nombre if ruta.chofer else "Sin asignar"

    return SeguimientoResponse(
        codigo=codigo,
        ruta_nombre=ruta.nombre,
        estado=ruta.estado,
        chofer_nombre=chofer_nombre,
        progreso=progreso,
        proxima_parada=proxima_parada,
        ultima_actualizacion=datetime.now(timezone(timedelta(hours=-3))),
        # Coordenadas actuales del chofer guardadas por PATCH /ubicacion
        # (si todavía no reportó ubicación, se muestra el punto de salida)
        chofer_latitud=ruta.chofer_latitud if ruta.chofer_latitud is not None else ruta.origen_latitud,
        chofer_longitud=ruta.chofer_longitud if ruta.chofer_longitud is not None else ruta.origen_longitud,
        fase=fase_ruta(ruta),
        retorno_descripcion=ruta.retorno_descripcion,
        retorno_latitud=ruta.retorno_latitud,
        retorno_longitud=ruta.retorno_longitud,
    )