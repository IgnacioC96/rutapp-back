# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.ruta import Ruta, EstadoRuta
from app.schemas.ruta import SeguimientoResponse, SeguimientoParadaResponse

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
    total_paradas = len(ruta.paradas)
    paradas_completadas = sum(1 for p in ruta.paradas if p.completada)
    progreso = int((paradas_completadas / total_paradas) * 100) if total_paradas > 0 else 0

    # Determinar la próxima parada (la primera no completada en orden)
    proxima_parada = None
    for parada in ruta.paradas:
        if not parada.completada:
            proxima_parada = SeguimientoParadaResponse(
                orden=parada.orden,
                cliente=parada.entrega.cliente.nombre,
                direccion=parada.entrega.direccion.descripcion,
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
        ultima_actualizacion=ruta.finalizada_en or ruta.iniciada_en or ruta.creada_en,
        # Coordenadas actuales del chofer guardadas por PATCH /ubicacion
        chofer_latitud=ruta.origen_latitud,
        chofer_longitud=ruta.origen_longitud,
    )