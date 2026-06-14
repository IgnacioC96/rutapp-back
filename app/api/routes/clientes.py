# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.database import get_db
from app.models.cliente import Cliente, DireccionCliente
from app.schemas.cliente import (
    ClienteCreate, ClienteUpdate,
    ClienteResponse, ClienteListResponse
)
from app.core.security import require_admin
import uuid

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.get("", response_model=ClienteListResponse)
def listar_clientes(
    search: Optional[str] = Query(None),
    solo_activos: bool = Query(True),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Lista todos los clientes con filtros opcionales.
    - search: busca por nombre o telefono
    - solo_activos: si es True solo devuelve clientes activos
    - Soporta paginacion
    """
    query = db.query(Cliente)

    if solo_activos:
        query = query.filter(Cliente.activo == True)

    if search:
        query = query.filter(
            Cliente.nombre.ilike(f"%{search}%") |
            Cliente.telefono_whatsapp.ilike(f"%{search}%")
        )

    total = query.count()
    clientes = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

    return ClienteListResponse(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        clientes=clientes
    )


@router.get("/{cliente_id}", response_model=ClienteResponse)
def obtener_cliente(
    cliente_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Devuelve el detalle de un cliente por su ID."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado"
        )
    return cliente


@router.post("", response_model=ClienteResponse, status_code=201)
def crear_cliente(
    datos: ClienteCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Crea un nuevo cliente con sus direcciones.
    Valida que haya entre 1 y 3 direcciones y exactamente una principal.
    """
    # Verificar que no exista un cliente con el mismo telefono
    existente = db.query(Cliente).filter(
        Cliente.telefono_whatsapp == datos.telefono_whatsapp,
        Cliente.activo == True
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un cliente activo con ese numero de WhatsApp"
        )

    # Crear el cliente
    nuevo_cliente = Cliente(
        nombre=datos.nombre,
        telefono_whatsapp=datos.telefono_whatsapp,
        cuit=datos.cuit,
        notas=datos.notas
    )
    db.add(nuevo_cliente)
    db.flush()  # Para obtener el ID sin hacer commit todavia

    # Crear las direcciones vinculadas al cliente
    for dir_data in datos.direcciones:
        direccion = DireccionCliente(
            cliente_id=nuevo_cliente.id,
            descripcion=dir_data.descripcion,
            referencia=dir_data.referencia,
            es_principal=dir_data.es_principal
        )
        db.add(direccion)

    db.commit()
    db.refresh(nuevo_cliente)
    return nuevo_cliente


@router.put("/{cliente_id}", response_model=ClienteResponse)
def editar_cliente(
    cliente_id: uuid.UUID,
    datos: ClienteUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Edita los datos de un cliente.
    Si se envian direcciones, reemplaza todas las existentes.
    """
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado"
        )

    # Actualizar solo los campos que vienen en el request
    if datos.nombre is not None:
        cliente.nombre = datos.nombre
    if datos.telefono_whatsapp is not None:
        cliente.telefono_whatsapp = datos.telefono_whatsapp
    if datos.cuit is not None:
        cliente.cuit = datos.cuit
    if datos.notas is not None:
        cliente.notas = datos.notas

    # Si vienen direcciones, eliminar las actuales y crear las nuevas
    if datos.direcciones is not None:
        db.query(DireccionCliente).filter(
            DireccionCliente.cliente_id == cliente_id
        ).delete()
        for dir_data in datos.direcciones:
            nueva_dir = DireccionCliente(
                cliente_id=cliente_id,
                descripcion=dir_data.descripcion,
                referencia=dir_data.referencia,
                es_principal=dir_data.es_principal
            )
            db.add(nueva_dir)

    db.commit()
    db.refresh(cliente)
    return cliente


@router.patch("/{cliente_id}/baja", response_model=ClienteResponse)
def dar_baja_cliente(
    cliente_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Da de baja logica a un cliente — no lo elimina de la BD.
    Sus entregas historicas se conservan.
    """
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado"
        )
    if not cliente.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El cliente ya esta dado de baja"
        )

    cliente.activo = False
    db.commit()
    db.refresh(cliente)
    return cliente