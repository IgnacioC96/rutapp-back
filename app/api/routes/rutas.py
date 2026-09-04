# -*- coding: utf-8 -*-
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.database import get_db
from app.models.ruta import Ruta, ParadaRuta, EstadoRuta
from app.models.entrega import Entrega, EstadoEntrega
from app.models.usuario import Usuario, RolUsuario
from app.schemas.ruta import (
    RutaCreate, RutaAsignar, RutaUpdate,
    RutaResponse, RutaListResponse,
    ConfirmarEntregaRequest, UbicacionRequest, SeguimientoResponse,
    SeguimientoParadaResponse, ReordenarParadasRequest, ParadaExtraCreate
)
from app.core.security import require_admin, get_current_user
from app.services.optimizacion import geocodificar_direccion, optimizar_ruta
from datetime import datetime, date
import uuid

router = APIRouter(prefix="/rutas", tags=["Rutas"])


@router.get("", response_model=RutaListResponse)
def listar_rutas(
    # Sprint 3 — filtros nuevos
    chofer_id: Optional[uuid.UUID] = Query(None),
    solo_plantillas: Optional[bool] = Query(None),
    fecha_programada: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista rutas según el rol del usuario y filtros opcionales.
    - Admin: ve todas las rutas
    - Chofer: ve solo las rutas asignadas a él
    Filtros opcionales: chofer_id, solo_plantillas, fecha_programada
    """
    query = db.query(Ruta)

    # Filtrar plantillas o rutas operativas según el parámetro
    if solo_plantillas is True:
        query = query.filter(Ruta.es_plantilla == True)
    elif solo_plantillas is False:
        query = query.filter(Ruta.es_plantilla == False)

    # El chofer solo ve sus rutas asignadas
    if current_user.get("rol") == "chofer":
        query = query.filter(Ruta.chofer_id == current_user.get("sub"))
    elif chofer_id:
        # El admin puede filtrar por chofer específico
        query = query.filter(Ruta.chofer_id == chofer_id)

    # Filtrar por fecha operativa
    if fecha_programada:
        query = query.filter(Ruta.fecha_programada == fecha_programada)

    rutas = query.order_by(Ruta.creada_en.desc()).all()

    return RutaListResponse(
        total=len(rutas),
        pagina=1,
        por_pagina=len(rutas),
        rutas=[RutaResponse.from_ruta(r) for r in rutas]
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
    1. Verifica que todas las entregas existan y estén pendientes
    2. Geocodifica el origen y las direcciones de cada entrega
    3. Calcula la matriz de distancias entre todos los puntos
    4. Aplica el algoritmo Nearest Neighbor para ordenar las paradas
    5. Guarda la ruta con las paradas en el orden optimizado
    6. Guarda las coordenadas geocodificadas en cada parada
    7. Cambia el estado de las entregas a "en_curso"
    """
    # Verificar que vengan entregas
    if not datos.entregas_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe incluir al menos una entrega"
        )

    # Verificar que todas las entregas existan y estén pendientes
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
                detail=f"La entrega {entrega_id} no está en estado pendiente"
            )
        entregas.append(entrega)

    # Geocodificar el punto de origen
    if datos.origen_latitud and datos.origen_longitud:
        # Si ya vienen coordenadas, usarlas directamente
        origen_coords = (datos.origen_longitud, datos.origen_latitud)
    elif datos.origen_descripcion:
        # Si viene descripción de texto, geocodificarla con ORS
        origen_coords = await geocodificar_direccion(datos.origen_descripcion)
        if not origen_coords:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo geocodificar la dirección de origen"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar el origen de la ruta"
        )

        # Obtener coordenadas de cada entrega
    # Prioridad: coordenadas guardadas en la dirección > geocodificación con ORS
    # Esto mejora la precisión cuando el admin ajustó el pin en el mapa de Alta Cliente
    coords_entregas = []
    entregas_sin_coords = []  # Índices de entregas que necesitan geocodificación

    for i, entrega in enumerate(entregas):
        if entrega.direccion.latitud and entrega.direccion.longitud:
            # Usar coordenadas guardadas — más precisas que geocodificar el texto
            # ORS usa (longitud, latitud) — mismo formato que guardamos
            coords_entregas.append((entrega.direccion.longitud, entrega.direccion.latitud))
        else:
            # No hay coordenadas guardadas — hay que geocodificar con ORS
            coords_entregas.append(None)
            entregas_sin_coords.append(i)

    # Geocodificar solo las entregas que no tienen coordenadas guardadas
    if entregas_sin_coords:
        tareas_geocoding = [
            geocodificar_direccion(entregas[i].direccion.descripcion)
            for i in entregas_sin_coords
        ]
        resultados = await asyncio.gather(*tareas_geocoding)

        # Asignar los resultados de geocodificación a las posiciones correspondientes
        for idx, resultado in zip(entregas_sin_coords, resultados):
            if resultado is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No se pudo geocodificar la dirección de la entrega {entregas[idx].id}"
                )
            coords_entregas[idx] = resultado

    # Optimizar el orden de las paradas con Nearest Neighbor
    orden_optimizado, total_km, tiempo_estimado_min = await optimizar_ruta(
        origen_coords, list(coords_entregas)
    )

    # Crear la ruta en la BD con los campos del Sprint 3
    nueva_ruta = Ruta(
        nombre=datos.nombre,
        origen_descripcion=datos.origen_descripcion,
        origen_latitud=datos.origen_latitud,
        origen_longitud=datos.origen_longitud,
        es_plantilla=datos.guardar_plantilla,
        fecha_programada=datos.fecha_programada,
        total_km=total_km,
        tiempo_estimado_min=tiempo_estimado_min
        # codigo_seguimiento se genera automáticamente en el modelo
    )
    db.add(nueva_ruta)
    db.flush()  # Obtener el ID sin hacer commit todavía

    # Crear las paradas en el orden optimizado
    # Guardamos también las coordenadas geocodificadas para el mapa
    for orden, idx_entrega in enumerate(orden_optimizado, start=1):
        entrega = entregas[idx_entrega]
        coords = coords_entregas[idx_entrega]  # (longitud, latitud)
        parada = ParadaRuta(
            ruta_id=nueva_ruta.id,
            entrega_id=entrega.id,
            orden=orden,
            # ORS devuelve (longitud, latitud) — las guardamos en el orden correcto
            longitud=coords[0],
            latitud=coords[1],
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
    Finaliza el recorrido.
    Si todas las entregas están completadas → estado 'completada'.
    Si quedan entregas sin confirmar → estado 'finalizada' (emergencia).
    Las entregas que quedaron en_curso vuelven a pendiente.
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

    # Verificar cuántas paradas quedaron sin confirmar
    paradas_pendientes = [p for p in ruta.paradas if not p.completada]

    if paradas_pendientes:
        # Finalización de emergencia — quedan entregas sin confirmar
        ruta.estado = EstadoRuta.finalizada
        # Las entregas asociadas vuelven a pendiente para ser reagendadas
        for parada in paradas_pendientes:
            parada.entrega.estado = EstadoEntrega.pendiente
    else:
        # Todas las paradas confirmadas — ruta completada exitosamente
        ruta.estado = EstadoRuta.completada

    ruta.finalizada_en = datetime.utcnow()
    db.commit()
    db.refresh(ruta)
    return RutaResponse.from_ruta(ruta)


# ── Sprint 3: endpoints nuevos ────────────────────────────────────────────────

@router.patch("/{ruta_id}/entregas/{entrega_id}/confirmar", response_model=RutaResponse)
def confirmar_entrega(
    ruta_id: uuid.UUID,
    entrega_id: uuid.UUID,
    datos: ConfirmarEntregaRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    El chofer confirma una entrega dentro de una ruta en curso.
    Verifica el código QR o manual ingresado por el chofer.
    Marca la parada como completada y la entrega como completada.
    """
    # Verificar que la ruta existe y está en curso
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada"
        )

    if ruta.estado != EstadoRuta.en_curso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden confirmar entregas en rutas en curso"
        )

    # Buscar la parada correspondiente a la entrega dentro de la ruta
    parada = db.query(ParadaRuta).filter(
        ParadaRuta.ruta_id == ruta_id,
        ParadaRuta.entrega_id == entrega_id
    ).first()
    if not parada:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no encontrada en esta ruta"
        )

    if parada.completada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta entrega ya fue confirmada"
        )

    # Verificar el código — debe coincidir con los últimos 6 caracteres
    # del ID de la entrega (código simple sin QR real por ahora)
    codigo_esperado = str(entrega_id).replace("-", "")[:6].upper()
    if datos.codigo.upper() != codigo_esperado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código incorrecto"
        )

    # Marcar la parada y la entrega como completadas
    parada.completada = True
    parada.entrega.estado = EstadoEntrega.completada

    db.commit()
    db.refresh(ruta)
    return RutaResponse.from_ruta(ruta)


@router.patch("/{ruta_id}/ubicacion")
def actualizar_ubicacion(
    ruta_id: uuid.UUID,
    datos: UbicacionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    El chofer reporta su ubicación GPS actual.
    El front llama a este endpoint cada 15 segundos durante el recorrido.
    La ubicación se guarda en la ruta para el seguimiento público en tiempo real.
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
            detail="Solo se puede reportar ubicación en rutas en curso"
        )

    # Guardar la última ubicación conocida del chofer en la ruta
    ruta.origen_latitud = datos.latitud
    ruta.origen_longitud = datos.longitud

    db.commit()
    return {"ok": True, "latitud": datos.latitud, "longitud": datos.longitud}

# ── Sprint 3: edición manual de rutas ────────────────────────────────────────

@router.patch("/{ruta_id}/paradas", response_model=RutaResponse)
def reordenar_paradas(
    ruta_id: uuid.UUID,
    datos: ReordenarParadasRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Reordena las paradas de una ruta manualmente.
    El admin arrastra las paradas en el front y manda el nuevo orden completo.
    Solo se puede reordenar rutas en estado pendiente o asignada.
    """
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada"
        )

    # Solo se puede editar si la ruta aún no fue iniciada
    if ruta.estado not in [EstadoRuta.pendiente, EstadoRuta.asignada]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden reordenar paradas en rutas pendientes o asignadas"
        )

    # Obtener todas las paradas actuales de la ruta
    paradas_actuales = {str(p.id): p for p in ruta.paradas}

    # Verificar que todos los IDs enviados pertenecen a esta ruta
    for item in datos.paradas:
        if str(item.parada_id) not in paradas_actuales:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La parada {item.parada_id} no pertenece a esta ruta"
            )

    # Aplicar el nuevo orden a cada parada
    for item in datos.paradas:
        parada = paradas_actuales[str(item.parada_id)]
        parada.orden = item.orden

    db.commit()
    db.refresh(ruta)
    return RutaResponse.from_ruta(ruta)


@router.post("/{ruta_id}/paradas/extra", response_model=RutaResponse, status_code=201)
def agregar_parada_extra(
    ruta_id: uuid.UUID,
    datos: ParadaExtraCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Agrega una parada extra a una ruta existente.
    Las paradas extra no son entregas a clientes — son paradas operativas
    como carga de nafta, almuerzo, parada técnica, etc.
    Solo se puede agregar en rutas pendientes o asignadas.
    """
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada"
        )

    # Solo se puede editar si la ruta aún no fue iniciada
    if ruta.estado not in [EstadoRuta.pendiente, EstadoRuta.asignada]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden agregar paradas en rutas pendientes o asignadas"
        )

    # Determinar el orden de la parada extra
    # Si no se especifica, va al final del recorrido
    if datos.orden is not None:
        orden_nueva = datos.orden
        # Desplazar las paradas existentes que tienen orden >= al nuevo
        for parada in ruta.paradas:
            if parada.orden >= orden_nueva:
                parada.orden += 1
    else:
        # Agregar al final — orden = máximo actual + 1
        orden_nueva = max((p.orden for p in ruta.paradas), default=0) + 1

    # Crear la parada extra sin entrega_id
    parada_extra = ParadaRuta(
        ruta_id=ruta_id,
        entrega_id=None,        # Las paradas extra no tienen entrega asociada
        orden=orden_nueva,
        es_parada_extra=True,
        descripcion_extra=datos.descripcion,
        direccion_extra=datos.direccion,
        latitud=datos.latitud,
        longitud=datos.longitud,
        completada=False
    )

    db.add(parada_extra)
    db.commit()
    db.refresh(ruta)
    return RutaResponse.from_ruta(ruta)
