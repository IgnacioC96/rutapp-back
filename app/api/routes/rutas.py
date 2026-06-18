# -*- coding: utf-8 -*-
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.db.database import get_db
from app.models.ruta import Ruta, ParadaRuta, EstadoRuta
from app.models.entrega import Entrega, EstadoEntrega
from app.models.usuario import Usuario, RolUsuario
from app.schemas.ruta import (
    RutaCreate, RutaAsignar, RutaUpdate,
    RutaResponse, RutaListResponse
)
from app.core.security import require_admin, get_current_user
from app.services.optimizacion import geocodificar_direccion, optimizar_ruta
from datetime import datetime
import uuid

router = APIRouter(prefix="/rutas", tags=["Rutas"])


@router.get("", response_model=RutaListResponse)
def listar_rutas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista rutas segun el rol del usuario:
    - Admin: ve todas las rutas
    - Chofer: ve solo las rutas asignadas a el
    """
    query = db.query(Ruta).filter(Ruta.es_plantilla == False)

    if current_user.get("rol") == "chofer":
        # El chofer solo ve sus propias rutas
        query = query.filter(Ruta.chofer_id == current_user.get("sub"))

    rutas = query.order_by(Ruta.creada_en.desc()).all()

    return RutaListResponse(
        total=len(rutas),
        pagina=1,
        por_pagina=len(rutas),
        rutas=rutas
    )


@router.get("/{ruta_id}", response_model=RutaResponse)
def obtener_ruta(
    ruta_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Devuelve el detalle de una ruta con sus paradas ordenadas."""
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada"
        )
    return RutaResponse.from_ruta(ruta)


@router.post("", response_model=RutaResponse, status_code=201)
async def crear_ruta(
    datos: RutaCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Crea una nueva ruta optimizando el orden de las entregas.

    Proceso:
    1. Verifica que todas las entregas existan y esten pendientes
    2. Geocodifica el origen y las direcciones de cada entrega
    3. Calcula la matriz de distancias entre todos los puntos
    4. Aplica el algoritmo Nearest Neighbor para ordenar las paradas
    5. Guarda la ruta con las paradas en el orden optimizado
    6. Cambia el estado de las entregas a "en_curso"
    """
    # Verificar que vengan entregas
    if not datos.entregas_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe incluir al menos una entrega"
        )

    # Verificar que todas las entregas existan y esten pendientes
    entregas = []
    for entrega_id in datos.entregas_ids:
        entrega = db.query(Entrega).filter(Entrega.id == entrega_id).first()
        if not entrega:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entrega {entrega_id} no encontrada"
            )
        if entrega.estado != EstadoEntrega.pendiente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La entrega {entrega_id} no esta en estado pendiente"
            )
        entregas.append(entrega)

    # Geocodificar el punto de origen
    if datos.origen_latitud and datos.origen_longitud:
        # Si ya vienen coordenadas, usarlas directamente
        origen_coords = (datos.origen_longitud, datos.origen_latitud)
    elif datos.origen_descripcion:
        # Si viene descripcion, geocodificarla
        origen_coords = await geocodificar_direccion(datos.origen_descripcion)
        if not origen_coords:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo geocodificar la direccion de origen"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar el origen de la ruta"
        )

    # Geocodificar las direcciones de cada entrega en paralelo
    # Usamos asyncio.gather para hacer todas las requests al mismo tiempo
    tareas_geocoding = [
        geocodificar_direccion(entrega.direccion.descripcion)
        for entrega in entregas
    ]
    coords_entregas = await asyncio.gather(*tareas_geocoding)

    # Verificar que todas las direcciones pudieron geocodificarse
    for i, coords in enumerate(coords_entregas):
        if coords is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se pudo geocodificar la direccion de la entrega {entregas[i].id}"
            )

    # Optimizar el orden de las paradas
    orden_optimizado, total_km, tiempo_estimado_min = await optimizar_ruta(origen_coords, list(coords_entregas))

    # Crear la ruta en la BD
    nueva_ruta = Ruta(
    nombre=datos.nombre,
    origen_descripcion=datos.origen_descripcion,
    origen_latitud=datos.origen_latitud,
    origen_longitud=datos.origen_longitud,
    es_plantilla=datos.guardar_plantilla,
    total_km=total_km,
    tiempo_estimado_min=tiempo_estimado_min
)
    db.add(nueva_ruta)
    db.flush()  # Para obtener el ID sin hacer commit

    # Crear las paradas en el orden optimizado
    for orden, idx_entrega in enumerate(orden_optimizado, start=1):
        entrega = entregas[idx_entrega]
        parada = ParadaRuta(
            ruta_id=nueva_ruta.id,
            entrega_id=entrega.id,
            orden=orden
        )
        db.add(parada)

        # Cambiar estado de la entrega a "en_curso"
        entrega.estado = EstadoEntrega.en_curso

    db.commit()
    db.refresh(nueva_ruta)
    return RutaResponse.from_ruta(nueva_ruta)


@router.patch("/{ruta_id}/asignar", response_model=RutaResponse)
def asignar_chofer(
    ruta_id: uuid.UUID,
    datos: RutaAsignar,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Asigna un chofer a una ruta pendiente.
    Verifica que el usuario exista y tenga rol de chofer.
    """
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada"
        )

    if ruta.estado != EstadoRuta.pendiente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se puede asignar chofer a rutas en estado pendiente"
        )

    # Verificar que el chofer existe y tiene el rol correcto
    chofer = db.query(Usuario).filter(
        Usuario.id == datos.chofer_id,
        Usuario.rol == RolUsuario.chofer,
        Usuario.activo == True
    ).first()
    if not chofer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chofer no encontrado o inactivo"
        )

    ruta.chofer_id = datos.chofer_id
    ruta.estado = EstadoRuta.asignada
    db.commit()
    db.refresh(ruta)
    return RutaResponse.from_ruta(ruta)


@router.patch("/{ruta_id}/iniciar", response_model=RutaResponse)
def iniciar_ruta(
    ruta_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    El chofer inicia el recorrido.
    Registra el timestamp exacto de inicio.
    Solo puede iniciarlo el chofer asignado a esa ruta.
    """
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada"
        )

    # Verificar que es el chofer asignado quien inicia
    if current_user.get("rol") == "chofer":
        if str(ruta.chofer_id) != current_user.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el chofer asignado puede iniciar esta ruta"
            )

    if ruta.estado != EstadoRuta.asignada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se puede iniciar una ruta en estado asignada"
        )

    ruta.estado = EstadoRuta.en_curso
    ruta.iniciada_en = datetime.utcnow()
    db.commit()
    db.refresh(ruta)
    return RutaResponse.from_ruta(ruta)


@router.patch("/{ruta_id}/finalizar", response_model=RutaResponse)
def finalizar_ruta(
    ruta_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Finaliza el recorrido — puede tener entregas pendientes (finalizacion de emergencia).
    Registra el timestamp de finalizacion.
    Si todas las entregas estan completadas, el estado es 'completada'.
    Si quedan entregas pendientes, el estado es 'finalizada' (emergencia).
    """
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada"
        )

    if ruta.estado != EstadoRuta.en_curso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se puede finalizar una ruta en estado en curso"
        )

    # Verificar cuantas entregas quedaron sin completar
    entregas_pendientes = [
        p for p in ruta.paradas
        if p.entrega.estado == EstadoEntrega.en_curso
    ]

    if entregas_pendientes:
        # Finalizacion de emergencia — quedan entregas sin completar
        ruta.estado = EstadoRuta.finalizada
        # Las entregas que quedaron en_curso vuelven a pendiente
        for parada in entregas_pendientes:
            parada.entrega.estado = EstadoEntrega.pendiente
    else:
        # Todas las entregas completadas
        ruta.estado = EstadoRuta.completada

    ruta.finalizada_en = datetime.utcnow()
    db.commit()
    db.refresh(ruta)
    return RutaResponse.from_ruta(ruta)