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
    SeguimientoParadaResponse, ReordenarParadasRequest, ParadaExtraCreate,
    ParadaExtraUpdate, RetornoTipo, fase_ruta, entregas_pendientes
)
from app.core.security import require_admin, get_current_user
from app.services.optimizacion import geocodificar_direccion, optimizar_ruta, ServicioMapasError
from app.core.exceptions import logger
from datetime import datetime, date
import uuid
import hmac
from app.core.geo import distancia_metros
from app.models.punto_salida import PuntoSalida

# Si el chofer está a menos de esta distancia del punto de retorno, la ruta se cierra sola
RADIO_LLEGADA_METROS = 150

router = APIRouter(prefix="/rutas", tags=["Rutas"])


def verificar_acceso_ruta(ruta: Ruta, current_user: dict) -> None:
    """
    Un chofer solo puede operar sobre rutas que tiene asignadas.
    El admin tiene acceso a todas. Se usa en todos los endpoints de ruta
    que no sean exclusivos de admin (ver, iniciar, finalizar, confirmar, ubicación).
    """
    if current_user.get("rol") == "chofer":
        if ruta.chofer_id is None or str(ruta.chofer_id) != current_user.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenés permiso para acceder a esta ruta"
            )


def _punto_activo(db: Session, punto_id: uuid.UUID, uso: str) -> PuntoSalida:
    punto = db.query(PuntoSalida).filter(PuntoSalida.id == punto_id, PuntoSalida.activo.is_(True)).first()
    if not punto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El punto de {uso} elegido ya no existe o fue dado de baja. Elegí otro"
        )
    return punto


def _error_servicio_mapas(exc: Exception) -> HTTPException:
    """503 con un mensaje claro cuando falla el servicio externo de mapas.
    No se modificó nada en la base: se puede reintentar sin problema."""
    logger.error(f"Servicio de mapas no disponible: {exc}")
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "No se pudo calcular la ruta porque el servicio de mapas no respondió. "
            "No se guardó nada: probá de nuevo en unos minutos"
        )
    )


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
    verificar_acceso_ruta(ruta, current_user)
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
            detail="Seleccioná al menos una entrega para planificar la ruta"
        )

    # Una misma entrega no puede estar dos veces en la ruta
    if len(set(datos.entregas_ids)) != len(datos.entregas_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hay entregas repetidas en la selección"
        )

    # Verificar que todas las entregas existan y estén pendientes
    entregas = []
    for entrega_id in datos.entregas_ids:
        entrega = db.query(Entrega).filter(Entrega.id == entrega_id).first()
        if not entrega:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Una de las entregas seleccionadas ya no existe. Actualizá la lista e intentá de nuevo"
            )
        if entrega.estado != EstadoEntrega.pendiente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"La entrega de {entrega.cliente.nombre} no está pendiente "
                    f"(estado actual: {entrega.estado.value}). Quitala de la selección"
                )
            )
        entregas.append(entrega)

    # Puntos de salida guardados: se copian a la ruta (si el punto cambia después, la ruta no)
    if datos.origen_punto_id:
        p_origen = _punto_activo(db, datos.origen_punto_id, "origen")
        datos.origen_descripcion = p_origen.descripcion
        datos.origen_latitud = p_origen.latitud
        datos.origen_longitud = p_origen.longitud
    if datos.retorno_punto_id:
        if datos.retorno_tipo == RetornoTipo.origen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Elegí una sola opción de retorno: volver al origen o a un punto guardado"
            )
        p_retorno = _punto_activo(db, datos.retorno_punto_id, "retorno")
        datos.retorno_tipo = RetornoTipo.otro
        datos.retorno_descripcion = p_retorno.descripcion
        datos.retorno_latitud = p_retorno.latitud
        datos.retorno_longitud = p_retorno.longitud

    # Geocodificar el punto de origen
    if datos.origen_latitud is not None and datos.origen_longitud is not None:
        # Si ya vienen coordenadas, usarlas directamente
        origen_coords = (datos.origen_longitud, datos.origen_latitud)
    elif datos.origen_descripcion:
        # Si viene descripción de texto, geocodificarla con ORS
        try:
            origen_coords = await geocodificar_direccion(datos.origen_descripcion)
        except ServicioMapasError as exc:
            raise _error_servicio_mapas(exc)
        if not origen_coords:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo geocodificar la dirección de origen"
            )
        # Guardar las coordenadas geocodificadas del origen en la ruta
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
        try:
            resultados = await asyncio.gather(*tareas_geocoding)
        except ServicioMapasError as exc:
            raise _error_servicio_mapas(exc)

        # Asignar los resultados de geocodificación a las posiciones correspondientes
        for idx, resultado in zip(entregas_sin_coords, resultados):
            if resultado is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"No se pudo ubicar en el mapa la dirección de la entrega de "
                        f"{entregas[idx].cliente.nombre} ({entregas[idx].direccion.descripcion}). "
                        f"Corregí la dirección o ajustá el pin del cliente"
                    )
                )
            coords_entregas[idx] = resultado

    # Punto de retorno (opcional): al origen, a otra dirección o ninguno
    retorno_coords = None          # (longitud, latitud), como ORS
    retorno_desc = None
    if datos.retorno_tipo == RetornoTipo.origen:
        retorno_coords = origen_coords
        retorno_desc = datos.origen_descripcion
    elif datos.retorno_tipo == RetornoTipo.otro:
        if datos.retorno_latitud is not None and datos.retorno_longitud is not None:
            retorno_coords = (datos.retorno_longitud, datos.retorno_latitud)
        else:
            try:
                retorno_coords = await geocodificar_direccion(datos.retorno_descripcion)
            except ServicioMapasError as exc:
                raise _error_servicio_mapas(exc)
            if not retorno_coords:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se pudo ubicar en el mapa la dirección de retorno. Revisala o marcá el punto en el mapa"
                )
        retorno_desc = datos.retorno_descripcion

    # Optimizar el orden de las paradas con Nearest Neighbor
    try:
        orden_optimizado, total_km, tiempo_estimado_min, retorno_km, retorno_min = await optimizar_ruta(
            origen_coords, list(coords_entregas), retorno_coords
        )
    except ServicioMapasError as exc:
        raise _error_servicio_mapas(exc)

    # Control de concurrencia: mientras se geocodificaba y optimizaba (varios segundos) otro
    # administrador pudo haber tomado alguna de estas entregas. Se vuelven a leer BLOQUEADAS
    # (SELECT ... FOR UPDATE) y se revalida el estado antes de escribir: así una misma entrega
    # nunca queda en dos rutas. Desde este punto hasta el commit no hay esperas intermedias.
    bloqueadas = {
        e.id: e for e in db.query(Entrega)
        .filter(Entrega.id.in_([e.id for e in entregas]))
        .with_for_update()
        .populate_existing()
        .all()
    }
    for e in entregas:
        actual = bloqueadas.get(e.id)
        if actual is None or actual.estado != EstadoEntrega.pendiente:
            nombre_cliente = e.cliente.nombre
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"La entrega de {nombre_cliente} fue tomada por otra ruta mientras planificabas. "
                    "Actualizá la lista de entregas pendientes e intentá de nuevo"
                )
            )

    # Crear la ruta en la BD con los campos del Sprint 3

    # Usar coordenadas del body si vienen, o las geocodificadas
    origen_lat_final = datos.origen_latitud if datos.origen_latitud is not None else (origen_coords[1] if origen_coords else None)
    origen_lon_final = datos.origen_longitud if datos.origen_longitud is not None else (origen_coords[0] if origen_coords else None)

    nueva_ruta = Ruta(
        nombre=datos.nombre,
        origen_descripcion=datos.origen_descripcion,
        origen_latitud=origen_lat_final,
        origen_longitud=origen_lon_final,
        es_plantilla=datos.guardar_plantilla,
        fecha_programada=datos.fecha_programada,
        total_km=total_km,
        tiempo_estimado_min=tiempo_estimado_min,
        retorno_tipo=datos.retorno_tipo.value,
        retorno_descripcion=retorno_desc,
        retorno_latitud=retorno_coords[1] if retorno_coords else None,
        retorno_longitud=retorno_coords[0] if retorno_coords else None,
        retorno_km=retorno_km if retorno_coords else None,
        retorno_min=retorno_min if retorno_coords else None
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

        # Cambiar estado de la entrega a "en_curso" y vincularla a su ruta actual
        # (de ahí sale qué entregas ve cada chofer)
        entrega.estado = EstadoEntrega.en_curso
        entrega.ruta_id = nueva_ruta.id

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
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).with_for_update().first()
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
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).with_for_update().first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada"
        )

    # Verificar que es el chofer asignado quien inicia
    verificar_acceso_ruta(ruta, current_user)

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
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).with_for_update().first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada"
        )

    verificar_acceso_ruta(ruta, current_user)

    # Si la ruta ya se cerró sola (última entrega sin retorno, o llegada al punto de retorno),
    # finalizar no falla: devuelve la ruta tal como quedó.
    if ruta.estado == EstadoRuta.completada:
        return RutaResponse.from_ruta(ruta)

    if ruta.estado != EstadoRuta.en_curso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se puede finalizar una ruta en estado en curso"
        )

    # Verificar cuántas paradas quedaron sin confirmar
    # Las paradas extra (es_parada_extra=True) no cuentan como pendientes
    paradas_pendientes = [
        p for p in ruta.paradas
        if not p.completada and not p.es_parada_extra
    ]

    if paradas_pendientes:
        # Finalización de emergencia — quedan entregas sin confirmar
        ruta.estado = EstadoRuta.finalizada
        # Las entregas asociadas vuelven a pendiente para ser reagendadas
        for parada in paradas_pendientes:
            if parada.entrega:  # Verificar que la parada tiene entrega asociada
                parada.entrega.estado = EstadoEntrega.pendiente
                parada.entrega.ruta_id = None  # queda libre para planificarla en otra ruta
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
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).with_for_update().first()
    if not ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta no encontrada"
        )

    verificar_acceso_ruta(ruta, current_user)

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

    # Verificar el código de confirmación.
    # Es un código aleatorio guardado en la entrega (NO derivado de su ID) que conoce
    # el destinatario. Se acepta el código solo o con prefijo "QR-" (contenido del QR).
    esperado = (parada.entrega.codigo_confirmacion or "").upper()
    if not esperado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La entrega no tiene código de confirmación. Contactá al administrador"
        )

    recibido = datos.codigo.strip().upper()
    if recibido.startswith("QR-"):
        recibido = recibido[3:]

    if not hmac.compare_digest(recibido.encode(), esperado.encode()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código incorrecto"
        )

    # Marcar la parada y la entrega como completadas
    parada.completada = True
    parada.entrega.estado = EstadoEntrega.completada

    # Si era la última entrega y la ruta no tiene retorno, se cierra sola.
    # Si tiene retorno, queda en curso en fase "regreso" hasta que el chofer llegue.
    db.flush()
    if (
        ruta.estado == EstadoRuta.en_curso
        and entregas_pendientes(ruta) == 0
        and (ruta.retorno_tipo or "ninguno") == "ninguno"
    ):
        ruta.estado = EstadoRuta.completada
        ruta.finalizada_en = datetime.utcnow()

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

    verificar_acceso_ruta(ruta, current_user)

    if ruta.estado != EstadoRuta.en_curso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se puede reportar ubicación en rutas en curso"
        )

    # Guardar la última ubicación conocida del chofer (ya no pisa el origen de la ruta)
    ruta.chofer_latitud = datos.latitud
    ruta.chofer_longitud = datos.longitud
    ruta.ubicacion_actualizada_en = datetime.utcnow()

    # Fase de regreso: si el chofer llegó al punto de retorno, la ruta se completa sola
    ruta_finalizada = False
    if (
        fase_ruta(ruta) == "regreso"
        and ruta.retorno_latitud is not None
        and ruta.retorno_longitud is not None
        and distancia_metros(datos.latitud, datos.longitud, ruta.retorno_latitud, ruta.retorno_longitud)
        <= RADIO_LLEGADA_METROS
    ):
        ruta.estado = EstadoRuta.completada
        ruta.finalizada_en = datetime.utcnow()
        ruta_finalizada = True

    db.commit()
    return {
        "ok": True,
        "latitud": datos.latitud,
        "longitud": datos.longitud,
        "fase": fase_ruta(ruta),
        "ruta_finalizada": ruta_finalizada
    }

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

    ids_enviados = [str(i.parada_id) for i in datos.paradas]
    if len(set(ids_enviados)) != len(ids_enviados):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hay paradas repetidas en el nuevo orden"
        )

    # El nuevo orden tiene que incluir TODAS las paradas de la ruta (una secuencia incompleta
    # dejaría paradas sin posición definida)
    if set(ids_enviados) != set(paradas_actuales):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El nuevo orden está incompleto: la ruta tiene {len(paradas_actuales)} paradas "
                f"y se enviaron {len(ids_enviados)}. Mandá todas las paradas"
            )
        )

    # Y las posiciones tienen que ser exactamente 1..N, sin repetir ni saltear
    posiciones = sorted(i.orden for i in datos.paradas)
    if posiciones != list(range(1, len(paradas_actuales) + 1)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nuevo orden es inválido: las posiciones deben ser 1, 2, 3… sin repetir ni saltear ninguna"
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
    max_orden = max((p.orden for p in ruta.paradas), default=0)
    if datos.orden is not None:
        # Si piden una posición más allá del final, va al final
        orden_nueva = min(datos.orden, max_orden + 1)
        # Desplazar las paradas existentes que tienen orden >= al nuevo
        for parada in ruta.paradas:
            if parada.orden >= orden_nueva:
                parada.orden += 1
    else:
        # Agregar al final — orden = máximo actual + 1
        orden_nueva = max_orden + 1

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


def _obtener_parada_extra_editable(db: Session, ruta_id: uuid.UUID, parada_id: uuid.UUID):
    """Devuelve (ruta, parada) si la parada es extra y la ruta todavía se puede editar."""
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id).first()
    if not ruta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ruta no encontrada")
    if ruta.estado not in [EstadoRuta.pendiente, EstadoRuta.asignada]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden modificar paradas en rutas pendientes o asignadas"
        )
    parada = next((p for p in ruta.paradas if p.id == parada_id), None)
    if not parada:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La parada no pertenece a esta ruta")
    if not parada.es_parada_extra:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden modificar o eliminar paradas extra, no las entregas"
        )
    return ruta, parada


@router.patch("/{ruta_id}/paradas/{parada_id}", response_model=RutaResponse)
def editar_parada_extra(
    ruta_id: uuid.UUID,
    parada_id: uuid.UUID,
    datos: ParadaExtraUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Edita una parada extra (descripción, dirección o coordenadas).
    Solo se pueden editar paradas extra de rutas pendientes o asignadas.
    Para quitar la dirección o las coordenadas, mandalas en null.
    """
    ruta, parada = _obtener_parada_extra_editable(db, ruta_id, parada_id)
    campos = datos.model_fields_set

    if "descripcion" in campos:
        if datos.descripcion is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La descripción de la parada no puede quedar vacía"
            )
        parada.descripcion_extra = datos.descripcion
    if "direccion" in campos:
        parada.direccion_extra = datos.direccion
    if "latitud" in campos or "longitud" in campos:
        lat = datos.latitud if "latitud" in campos else parada.latitud
        lon = datos.longitud if "longitud" in campos else parada.longitud
        if (lat is None) != (lon is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mandá latitud y longitud juntas, o ninguna de las dos"
            )
        parada.latitud = lat
        parada.longitud = lon

    db.commit()
    db.refresh(ruta)
    return RutaResponse.from_ruta(ruta)


@router.delete("/{ruta_id}/paradas/{parada_id}", response_model=RutaResponse)
def eliminar_parada_extra(
    ruta_id: uuid.UUID,
    parada_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Elimina una parada extra de una ruta pendiente o asignada y reordena las que siguen
    (el orden vuelve a quedar 1, 2, 3... sin huecos). Las paradas de entrega no se
    pueden eliminar por acá. Devuelve la ruta actualizada.
    """
    ruta, parada = _obtener_parada_extra_editable(db, ruta_id, parada_id)

    db.delete(parada)
    db.flush()
    restantes = sorted((p for p in ruta.paradas if p.id != parada_id), key=lambda p: p.orden)
    for nuevo, p in enumerate(restantes, start=1):
        p.orden = nuevo

    db.commit()
    db.refresh(ruta)
    return RutaResponse.from_ruta(ruta)
