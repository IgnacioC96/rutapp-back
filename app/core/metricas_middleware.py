# -*- coding: utf-8 -*-
"""
Middleware que registra, sin tocar los endpoints, las operaciones de negocio (crear, editar,
eliminar, confirmar entrega, etc.), los ingresos rechazados y las visitas al seguimiento público.

Mide también cuánto tardó la API en responder (duracion_ms), dato clave para detectar cuellos
de botella. Cualquier error de la analítica se atrapa: nunca afecta la respuesta al usuario.
"""
import time
from starlette.concurrency import run_in_threadpool
from fastapi import Request

from app.core.exceptions import logger
from app.core.security import verificar_token
from app.db.database import get_db
from app.services import metricas


def _guardar(app, info, payload, status, duracion_ms, user_agent):
    # Respeta los overrides de get_db (los tests usan su propia base)
    gen = (app.dependency_overrides.get(get_db) or get_db)()
    db = next(gen)
    try:
        metricas.registrar_peticion(db, info, payload, status, duracion_ms, user_agent)
    finally:
        gen.close()


async def registrar_actividad(request: Request, call_next):
    inicio = time.perf_counter()
    response = await call_next(request)
    try:
        if request.method != "OPTIONS":
            info = metricas.clasificar(request.method, request.url.path, response.status_code,
                                       dict(request.query_params))
            if info:
                payload = None
                auth = request.headers.get("authorization", "")
                if auth.lower().startswith("bearer "):
                    payload = verificar_token(auth[7:])
                duracion = int((time.perf_counter() - inicio) * 1000)
                await run_in_threadpool(_guardar, request.app, info, payload, response.status_code,
                                        duracion, request.headers.get("user-agent"))
    except Exception as exc:
        logger.warning(f"métricas: middleware: {exc}")
    return response
