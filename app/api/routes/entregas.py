# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.database import get_db
from app.models.entrega import Entrega, EstadoEntrega
from app.models.cliente import Cliente, DireccionCliente
from app.schemas.entrega import (
    EntregaCreate, EntregaUpdate,
    EntregaResponse, EntregaListResponse
)
from app.core.security import require_admin, get_current_user
import uuid

router = APIRouter(prefix="/entregas", tags=["Entregas"])


@router.get("", response_model=EntregaListResponse)
def listar_entregas(
    estado: Optional[str] = Query(None),
    cliente_id: Optional[uuid.UUID] = Query(None),
    search: Optional[str] = Query(None),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista entregas con filtros opcionales.
    Admin ve todas, chofer ve solo las de sus rutas.
    """
    query = db.query(Entrega)

    if estado:
        try:
            estado_enum = EstadoEntrega[estado]
            query = query.filter(Entrega.estado == estado_enum)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Estado invalido. Opciones: {[e.value for e in EstadoEntrega]}"
            )

    if cliente_id:
        query = query.filter(Entrega.cliente_id == cliente_id)

    if search:
        query = query.join(Cliente).filter(
            Cliente.nombre.ilike(f"%{search}%")
        )

    total = query.count()
    entregas = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

    return EntregaListResponse(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        entregas=entregas
    )


@router.get("/{entrega_id}", response_model=EntregaResponse)
def obtener_entrega(
    entrega_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Devuelve el detalle de una entrega por su ID."""
    entrega = db.query(Entrega).filter(Entrega.id == entrega_id).first()
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no encontrada"
        )
    return entrega


@router.post("", response_model=EntregaResponse, status_code=201)
def crear_entrega(
    datos: EntregaCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Crea una nueva entrega vinculada a un cliente y una direccion.
    Verifica que el cliente y la direccion existan y esten activos.
    """
    # Verificar que el cliente existe y esta activo
    cliente = db.query(Cliente).filter(
        Cliente.id == datos.cliente_id,
        Cliente.activo == True
    ).first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado o inactivo"
        )

    # Verificar que la direccion pertenece al cliente
    direccion = db.query(DireccionCliente).filter(
        DireccionCliente.id == datos.direccion_id,
        DireccionCliente.cliente_id == datos.cliente_id
    ).first()
    if not direccion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Direccion no encontrada o no pertenece al cliente"
        )

    nueva_entrega = Entrega(
        cliente_id=datos.cliente_id,
        direccion_id=datos.direccion_id,
        descripcion=datos.descripcion,
        bultos=datos.bultos,
        peso_kg=datos.peso_kg,
        fecha_estimada=datos.fecha_estimada,
        observaciones=datos.observaciones
    )

    db.add(nueva_entrega)
    db.commit()
    db.refresh(nueva_entrega)
    return nueva_entrega


@router.put("/{entrega_id}", response_model=EntregaResponse)
def editar_entrega(
    entrega_id: uuid.UUID,
    datos: EntregaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Edita una entrega existente.
    Solo se pueden editar entregas en estado pendiente.
    """
    entrega = db.query(Entrega).filter(Entrega.id == entrega_id).first()
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no encontrada"
        )

    if entrega.estado != EstadoEntrega.pendiente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden editar entregas en estado pendiente"
        )

    # Si cambia la direccion, verificar que pertenece al mismo cliente
    if datos.direccion_id:
        direccion = db.query(DireccionCliente).filter(
            DireccionCliente.id == datos.direccion_id,
            DireccionCliente.cliente_id == entrega.cliente_id
        ).first()
        if not direccion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Direccion no encontrada o no pertenece al cliente"
            )
        entrega.direccion_id = datos.direccion_id

    if datos.descripcion is not None:
        entrega.descripcion = datos.descripcion
    if datos.bultos is not None:
        entrega.bultos = datos.bultos
    if datos.peso_kg is not None:
        entrega.peso_kg = datos.peso_kg
    if datos.fecha_estimada is not None:
        entrega.fecha_estimada = datos.fecha_estimada
    if datos.observaciones is not None:
        entrega.observaciones = datos.observaciones

    db.commit()
    db.refresh(entrega)
    return entrega


@router.patch("/{entrega_id}/cancelar", response_model=EntregaResponse)
def cancelar_entrega(
    entrega_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Cancela una entrega. Solo se pueden cancelar entregas pendientes.
    """
    entrega = db.query(Entrega).filter(Entrega.id == entrega_id).first()
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no encontrada"
        )

    if entrega.estado != EstadoEntrega.pendiente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden cancelar entregas en estado pendiente"
        )

    entrega.estado = EstadoEntrega.cancelada
    db.commit()
    db.refresh(entrega)
    return entrega


@router.patch("/{entrega_id}/completar", response_model=EntregaResponse)
def completar_entrega(
    entrega_id: uuid.UUID,
    observaciones_chofer: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Marca una entrega como completada. Lo hace el chofer al confirmar con QR.
    """
    entrega = db.query(Entrega).filter(Entrega.id == entrega_id).first()
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no encontrada"
        )

    if entrega.estado != EstadoEntrega.en_curso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden completar entregas en estado en curso"
        )

    entrega.estado = EstadoEntrega.completada
    if observaciones_chofer:
        entrega.observaciones_chofer = observaciones_chofer

    db.commit()
    db.refresh(entrega)
    return entrega