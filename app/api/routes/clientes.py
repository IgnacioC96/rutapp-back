# -*- coding: utf-8 -*-
"""
Endpoints para la gestión de clientes y sus direcciones.
Solo accesibles por usuarios con rol admin.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.database import get_db
from app.models.cliente import Cliente, DireccionCliente
from app.models.entrega import Entrega
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
    - search: busca por nombre o teléfono
    - solo_activos: si es True solo devuelve clientes activos
    - Soporta paginación
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
    Sprint 3: guarda coordenadas del pin del mapa si vienen en el request.
    """
    # Verificar que no exista un cliente con el mismo teléfono
    existente = db.query(Cliente).filter(
        Cliente.telefono_whatsapp == datos.telefono_whatsapp,
        Cliente.activo == True
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un cliente activo con ese número de WhatsApp"
        )

    # Crear el cliente
    nuevo_cliente = Cliente(
        nombre=datos.nombre,
        telefono_whatsapp=datos.telefono_whatsapp,
        cuit=datos.cuit,
        notas=datos.notas
    )
    db.add(nuevo_cliente)
    db.flush()  # Para obtener el ID sin hacer commit todavía

    # Crear las direcciones vinculadas al cliente
    # Sprint 3: incluye latitud y longitud si el front las mandó desde el mapa
    for dir_data in datos.direcciones:
        direccion = DireccionCliente(
            cliente_id=nuevo_cliente.id,
            descripcion=dir_data.descripcion,
            referencia=dir_data.referencia,
            es_principal=dir_data.es_principal,
            latitud=dir_data.latitud,
            longitud=dir_data.longitud
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
    Edita los datos de un cliente y sus direcciones.
    Actualiza las direcciones existentes sin borrar las que tienen entregas.
    Sprint 3: guarda coordenadas del pin del mapa si vienen en el request.
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

    if datos.direcciones is not None:
        direcciones_existentes = db.query(DireccionCliente).filter(
            DireccionCliente.cliente_id == cliente_id
        ).all()
        ids_existentes = {str(d.id): d for d in direcciones_existentes}
        ids_recibidos = []

        for dir_data in datos.direcciones:
            if dir_data.id and str(dir_data.id) in ids_existentes:
                # Actualizar dirección existente — incluye coordenadas del mapa
                dir_obj = ids_existentes[str(dir_data.id)]
                dir_obj.descripcion = dir_data.descripcion
                dir_obj.referencia = dir_data.referencia
                dir_obj.es_principal = dir_data.es_principal
                # Sprint 3: actualizar coordenadas si vienen del mapa
                if dir_data.latitud is not None:
                    dir_obj.latitud = dir_data.latitud
                if dir_data.longitud is not None:
                    dir_obj.longitud = dir_data.longitud
                ids_recibidos.append(str(dir_data.id))
            else:
                # Crear dirección nueva con coordenadas del mapa si vienen
                nueva_dir = DireccionCliente(
                    cliente_id=cliente_id,
                    descripcion=dir_data.descripcion,
                    referencia=dir_data.referencia,
                    es_principal=dir_data.es_principal,
                    latitud=dir_data.latitud,
                    longitud=dir_data.longitud
                )
                db.add(nueva_dir)

        # Borrar solo las direcciones que no tienen entregas asociadas
        for id_existente, dir_obj in ids_existentes.items():
            if id_existente not in ids_recibidos:
                tiene_entregas = db.query(Entrega).filter(
                    Entrega.direccion_id == dir_obj.id
                ).first()
                if not tiene_entregas:
                    db.delete(dir_obj)

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
    Da de baja lógica a un cliente — no lo elimina de la BD.
    Sus entregas históricas se conservan para trazabilidad.
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
            detail="El cliente ya está dado de baja"
        )

    cliente.activo = False
    db.commit()
    db.refresh(cliente)
    return cliente