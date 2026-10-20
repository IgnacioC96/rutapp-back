# -*- coding: utf-8 -*-
"""
Manejo centralizado de excepciones y errores custom para RutApp.
Define handlers globales que interceptan errores y devuelven
respuestas consistentes en formato JSON con códigos descriptivos.
"""
import logging
import json
from datetime import datetime
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError


# ── Configuración del logger estructurado ────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """
    Formatter que emite cada log como una línea JSON.
    Facilita la ingesta en herramientas de observabilidad
    como Datadog, Loki o CloudWatch.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            # Incluir info de excepción si existe
            "exc_info": self.formatException(record.exc_info) if record.exc_info else None,
        }
        # Eliminar campos nulos para mantener el JSON limpio
        return json.dumps({k: v for k, v in log_entry.items() if v is not None})


def setup_logging():
    """
    Configura el sistema de logging de la aplicación.
    Usa formato JSON para facilitar la observabilidad en producción.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    # Logger raíz de la aplicación
    logger = logging.getLogger("rutapp")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False

    return logger


# Logger global — importarlo en cualquier módulo con:
# from app.core.exceptions import logger
logger = setup_logging()


# ── Exception Handlers ────────────────────────────────────────────────────────

def _mensaje_en_espanol(error: dict) -> str:
    """Traduce los mensajes de validación de Pydantic a español claro para el usuario."""
    tipo = error.get("type", "")
    msg = error.get("msg", "")
    ctx = error.get("ctx") or {}
    campo = str(error["loc"][-1]) if error.get("loc") else ""

    if tipo == "missing":
        return "Este campo es obligatorio"
    if tipo == "string_too_short":
        return f"Debe tener al menos {ctx.get('min_length')} caracteres"
    if tipo == "string_too_long":
        return f"Puede tener como máximo {ctx.get('max_length')} caracteres"
    if tipo in ("greater_than", "greater_than_equal"):
        limite = ctx.get("gt", ctx.get("ge"))
        return f"Debe ser mayor a {limite}" if tipo == "greater_than" else f"Debe ser como mínimo {limite}"
    if tipo in ("less_than", "less_than_equal"):
        limite = ctx.get("lt", ctx.get("le"))
        return f"Debe ser menor a {limite}" if tipo == "less_than" else f"Debe ser como máximo {limite}"
    if tipo in ("int_parsing", "float_parsing", "int_from_float", "decimal_parsing"):
        return "Debe ser un número válido"
    if tipo in ("string_type", "str_type"):
        return "Debe ser un texto"
    if tipo == "bool_parsing" or tipo == "bool_type":
        return "Debe ser verdadero o falso"
    if tipo in ("date_parsing", "date_from_datetime_parsing", "date_type"):
        return "Fecha inválida: usá el formato AAAA-MM-DD"
    if tipo in ("datetime_parsing", "datetime_type"):
        return "Fecha y hora inválidas"
    if tipo == "uuid_parsing":
        return "Identificador inválido"
    if tipo in ("enum", "literal_error"):
        return "Valor no permitido"
    if tipo == "json_invalid":
        return "El cuerpo de la petición no es un JSON válido"
    if tipo in ("list_type", "too_short"):
        return "Debe ser una lista con al menos un elemento" if tipo == "too_short" else "Debe ser una lista"
    if tipo == "value_error":
        if campo == "email" or "email address" in msg:
            return "El email no es válido"
        # Los validadores propios ya devuelven el mensaje en español
        return msg.removeprefix("Value error, ")
    return msg


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Intercepta errores de validación de Pydantic (422 Unprocessable Entity).
    Devuelve un mensaje legible con los campos que fallaron.
    """
    errores = []
    for error in exc.errors():
        campo = " → ".join(str(e) for e in error["loc"] if e != "body")
        errores.append({
            "campo": campo,
            "mensaje": _mensaje_en_espanol(error),
            "tipo": error["type"]
        })

    logger.warning(f"Error de validación en {request.method} {request.url.path}: {errores}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "datos_invalidos",
            "mensaje": "Los datos enviados no son válidos",
            "detalle": errores
        }
    )


async def integrity_error_handler(request: Request, exc: IntegrityError):
    """
    Intercepta errores de integridad de PostgreSQL.
    Cubre violaciones de FK y unique constraints.
    Devuelve un mensaje amigable en vez del error crudo de la BD.
    """
    logger.error(f"Error de integridad en {request.method} {request.url.path}: {str(exc)}")

    error_str = str(exc.orig).lower() if exc.orig else ""

    if "unique" in error_str or "duplicate" in error_str:
        mensaje = "Ya existe un registro con esos datos únicos"
    elif "foreign key" in error_str or "violates foreign key" in error_str:
        mensaje = "No se puede realizar la operación porque el registro está referenciado por otros datos"
    else:
        mensaje = "Error de integridad en la base de datos"

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "conflicto_de_datos",
            "mensaje": mensaje
        }
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """
    Captura cualquier excepción no manejada explícitamente.
    Loguea el error completo y devuelve un 500 genérico al cliente.
    Evita exponer detalles internos del sistema en producción.
    """
    logger.error(
        f"Error inesperado en {request.method} {request.url.path}: {str(exc)}",
        exc_info=True
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "error_interno",
            "mensaje": "Ocurrió un error inesperado. Por favor intentá de nuevo."
        }
    )


async def http_exception_handler(request: Request, exc):
    """
    Intercepta HTTPExceptions de FastAPI y las loguea antes de responder.
    Mantiene el status code original pero agrega logging estructurado.
    Los errores 5xx se loguean como ERROR, los 4xx como WARNING.
    """
    if exc.status_code >= 500:
        logger.error(f"HTTP {exc.status_code} en {request.method} {request.url.path}: {exc.detail}")
    elif exc.status_code >= 400:
        logger.warning(f"HTTP {exc.status_code} en {request.method} {request.url.path}: {exc.detail}")

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "mensaje": exc.detail}
    )