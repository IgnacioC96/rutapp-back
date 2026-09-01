# -*- coding: utf-8 -*-
"""
Endpoints para la gestión de flota de vehículos.
Solo accesibles por usuarios con rol admin.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.database import get_db
from app.models.vehiculo import Vehiculo, EstadoVehiculo
from app.models.usuario import Usuario, RolUsuario
from app.schemas.vehiculo import (
    VehiculoCreate, VehiculoUpdate,
    VehiculoResponse, VehiculoListResponse
)
from app.core.security import require_admin
import uuid

router = APIRouter(prefix="/vehiculos", tags=["Flota"])


@router.get("", response_model=VehiculoListResponse)
def listar_vehiculos(
    # Filtro opcional por estado operativo
    estado: Optional[str] = Query(None),
    # Filtro opcional por chofer asignado
    chofer_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Lista todos los vehículos de la flota.
    Filtros opcionales: estado (disponible/en_ruta/mantenimiento) y chofer_id.
    Solo accesible por admin.
    """
    query = db.query(Vehiculo)

    # Aplicar filtro por estado si viene en el query
    if estado:
        try:
            estado_enum = EstadoVehiculo[estado]
            query = query.filter(Vehiculo.estado == estado_enum)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Estado inválido. Opciones: {[e.value for e in EstadoVehiculo]}"
            )

    # Aplicar filtro por chofer si viene en el query
    if chofer_id:
        query = query.filter(Vehiculo.chofer_id == chofer_id)

    vehiculos = query.order_by(Vehiculo.patente).all()

    return VehiculoListResponse(
        total=len(vehiculos),
        vehiculos=[VehiculoResponse.from_vehiculo(v) for v in vehiculos]
    )


@router.get("/{vehiculo_id}", response_model=VehiculoResponse)
def obtener_vehiculo(
    vehiculo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Devuelve el detalle de un vehículo por su ID."""
    vehiculo = db.query(Vehiculo).filter(Vehiculo.id == vehiculo_id).first()
    if not vehiculo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehículo no encontrado"
        )
    return VehiculoResponse.from_vehiculo(vehiculo)


@router.post("", response_model=VehiculoResponse, status_code=201)
def crear_vehiculo(
    datos: VehiculoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Da de alta un nuevo vehículo en la flota.
    Verifica que la patente no esté duplicada.
    Si viene chofer_id, verifica que el chofer exista y tenga rol correcto.
    """
    # Verificar que la patente no esté registrada
    existente = db.query(Vehiculo).filter(
        Vehiculo.patente == datos.patente
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe un vehículo con la patente {datos.patente}"
        )

    # Si viene chofer_id, verificar que el chofer existe y está activo
    if datos.chofer_id:
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

    nuevo_vehiculo = Vehiculo(
        patente=datos.patente,
        marca_modelo=datos.marca_modelo,
        capacidad_kg=datos.capacidad_kg,
        chofer_id=datos.chofer_id
        # estado queda en 'disponible' por defecto
    )

    db.add(nuevo_vehiculo)
    db.commit()
    db.refresh(nuevo_vehiculo)
    return VehiculoResponse.from_vehiculo(nuevo_vehiculo)


@router.put("/{vehiculo_id}", response_model=VehiculoResponse)
def editar_vehiculo(
    vehiculo_id: uuid.UUID,
    datos: VehiculoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Edita los datos de un vehículo existente.
    Permite actualizar marca/modelo, capacidad, estado y chofer asignado.
    """
    vehiculo = db.query(Vehiculo).filter(Vehiculo.id == vehiculo_id).first()
    if not vehiculo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehículo no encontrado"
        )

    # Actualizar solo los campos que vienen en el request
    if datos.marca_modelo is not None:
        vehiculo.marca_modelo = datos.marca_modelo
    if datos.capacidad_kg is not None:
        vehiculo.capacidad_kg = datos.capacidad_kg
    if datos.estado is not None:
        vehiculo.estado = EstadoVehiculo[datos.estado.value]

    # Reasignar o desasignar chofer
    if datos.chofer_id is not None:
        # Verificar que el nuevo chofer existe y tiene el rol correcto
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
        vehiculo.chofer_id = datos.chofer_id

    db.commit()
    db.refresh(vehiculo)
    return VehiculoResponse.from_vehiculo(vehiculo)


@router.delete("/{vehiculo_id}", status_code=204)
def eliminar_vehiculo(
    vehiculo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Elimina un vehículo de la flota.
    Solo se puede eliminar si no está en estado 'en_ruta'.
    A diferencia de clientes y entregas, la eliminación es física
    ya que un vehículo dado de baja no necesita trazabilidad histórica.
    """
    vehiculo = db.query(Vehiculo).filter(Vehiculo.id == vehiculo_id).first()
    if not vehiculo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehículo no encontrado"
        )

    # No se puede eliminar un vehículo que está actualmente en ruta
    if vehiculo.estado == EstadoVehiculo.en_ruta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar un vehículo que está en ruta"
        )

    db.delete(vehiculo)
    db.commit()