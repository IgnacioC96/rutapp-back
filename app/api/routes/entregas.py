# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime, timezone, timedelta
from app.db.database import get_db
from app.models.entrega import Entrega, EstadoEntrega
from app.models.cliente import Cliente, DireccionCliente
from app.models.ruta import Ruta
from app.schemas.entrega import (
    EntregaCreate, EntregaUpdate,
    EntregaResponse, EntregaListResponse
)
from app.core.security import require_admin, get_current_user
import uuid

router = APIRouter(prefix="/entregas", tags=["Entregas"])

# Argentina no tiene horario de verano: UTC-3 fijo (mismo criterio que seguimiento.py).
# El servidor puede estar en UTC, así que "hoy" se calcula con esta zona y no con date.today().
ZONA_ARGENTINA = timezone(timedelta(hours=-3))


def _hoy_argentina() -> date:
    return datetime.now(ZONA_ARGENTINA).date()


def _query_entregas_visibles(db: Session, current_user: dict):
    """
    Base de consulta común a los listados:
    el admin ve todas las entregas; el chofer solo las de las rutas que tiene asignadas.
    """
    query = db.query(Entrega)
    if current_user.get("rol") != "admin":
        query = query.join(Ruta, Entrega.ruta_id == Ruta.id).filter(
            Ruta.chofer_id == uuid.UUID(current_user.get("sub"))
        )
    return query


def _ordenar_entregas(query):
    """Orden estable (necesario para paginar): primero las más próximas, sin fecha al final."""
    return query.order_by(
        Entrega.fecha_estimada.asc().nulls_last(),
        Entrega.creada_en.desc(),
        Entrega.id,
    )


@router.get("", response_model=EntregaListResponse)
def listar_entregas(
    estado: Optional[str] = Query(None),
    cliente_id: Optional[uuid.UUID] = Query(None),
    search: Optional[str] = Query(None),
    fecha_estimada: Optional[date] = Query(None, description="Solo entregas con esa fecha estimada exacta"),
    fecha_desde: Optional[date] = Query(None, description="Fecha estimada desde (inclusive)"),
    fecha_hasta: Optional[date] = Query(None, description="Fecha estimada hasta (inclusive)"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista entregas con filtros opcionales.
    Admin ve todas, chofer ve solo las de sus rutas.
    Filtros de fecha: fecha_estimada (exacta) o fecha_desde/fecha_hasta (rango).
    Orden: fecha estimada más próxima primero; las que no tienen fecha, al final.
    """
    es_admin = current_user.get("rol") == "admin"
    query = _query_entregas_visibles(db, current_user)

    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fecha_desde no puede ser posterior a fecha_hasta"
        )
    if fecha_estimada:
        query = query.filter(Entrega.fecha_estimada == fecha_estimada)
    if fecha_desde:
        query = query.filter(Entrega.fecha_estimada >= fecha_desde)
    if fecha_hasta:
        query = query.filter(Entrega.fecha_estimada <= fecha_hasta)

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
    entregas = _ordenar_entregas(query).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

    return EntregaListResponse(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        entregas=[EntregaResponse.from_entrega(e, incluir_codigo=es_admin) for e in entregas]
    )


# IMPORTANTE: esta ruta va ANTES de "/{entrega_id}"; si no, FastAPI intentaría
# interpretar "pendientes-hoy" como un UUID y respondería 422.
@router.get("/pendientes-hoy", response_model=EntregaListResponse)
def listar_pendientes_hoy(
    incluir_atrasadas: bool = Query(
        False,
        description="Si es true, suma las pendientes con fecha estimada anterior a hoy"
    ),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Entregas pendientes cuya fecha estimada es HOY (hora de Argentina).
    Pensado para el dashboard del admin y para armar la ruta del día.
    Con incluir_atrasadas=true también trae las pendientes de días anteriores
    que quedaron sin entregar. El campo total sirve como contador del dashboard.
    """
    es_admin = current_user.get("rol") == "admin"
    hoy = _hoy_argentina()
    query = _query_entregas_visibles(db, current_user).filter(
        Entrega.estado == EstadoEntrega.pendiente
    )
    if incluir_atrasadas:
        query = query.filter(Entrega.fecha_estimada <= hoy)
    else:
        query = query.filter(Entrega.fecha_estimada == hoy)

    total = query.count()
    entregas = _ordenar_entregas(query).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

    return EntregaListResponse(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        entregas=[EntregaResponse.from_entrega(e, incluir_codigo=es_admin) for e in entregas]
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

    es_admin = current_user.get("rol") == "admin"
    if not es_admin:
        # El chofer solo puede ver entregas de rutas que tiene asignadas
        # (404 y no 403 para no revelar que la entrega existe)
        if not entrega.ruta or str(entrega.ruta.chofer_id) != current_user.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrega no encontrada"
            )
    return EntregaResponse.from_entrega(entrega, incluir_codigo=es_admin)


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
        largo_cm=datos.largo_cm,
        ancho_cm=datos.ancho_cm,
        alto_cm=datos.alto_cm,
        fecha_estimada=datos.fecha_estimada,
        observaciones=datos.observaciones
    )

    db.add(nueva_entrega)
    db.commit()
    db.refresh(nueva_entrega)
    return EntregaResponse.from_entrega(nueva_entrega, incluir_codigo=True)


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
    entrega = db.query(Entrega).filter(Entrega.id == entrega_id).with_for_update().first()
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
    if datos.largo_cm is not None:
        entrega.largo_cm = datos.largo_cm
    if datos.ancho_cm is not None:
        entrega.ancho_cm = datos.ancho_cm
    if datos.alto_cm is not None:
        entrega.alto_cm = datos.alto_cm
    if datos.fecha_estimada is not None:
        entrega.fecha_estimada = datos.fecha_estimada
    if datos.observaciones is not None:
        entrega.observaciones = datos.observaciones

    db.commit()
    db.refresh(entrega)
    return EntregaResponse.from_entrega(entrega, incluir_codigo=True)


@router.patch("/{entrega_id}/cancelar", response_model=EntregaResponse)
def cancelar_entrega(
    entrega_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Cancela una entrega. Solo se pueden cancelar entregas pendientes.
    """
    entrega = db.query(Entrega).filter(Entrega.id == entrega_id).with_for_update().first()
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
    return EntregaResponse.from_entrega(entrega, incluir_codigo=True)


@router.patch("/{entrega_id}/completar", response_model=EntregaResponse)
def completar_entrega(
    entrega_id: uuid.UUID,
    observaciones_chofer: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Cierre MANUAL de una entrega por el administrador (excepción operativa).
    La confirmación del chofer en campo se hace SOLO con
    PATCH /rutas/{ruta_id}/entregas/{entrega_id}/confirmar, que exige el código secreto.
    """
    entrega = db.query(Entrega).filter(Entrega.id == entrega_id).with_for_update().first()
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
    return EntregaResponse.from_entrega(entrega, incluir_codigo=True)