# -*- coding: utf-8 -*-
"""
Servicio de métricas de uso: captura (sesiones, eventos, navegación) y consultas de análisis.

Principio de diseño: la analítica NUNCA debe romper la aplicación. Toda función de captura
atrapa sus errores y los deja en el log; si falla, el usuario ni se entera.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import logger
from app.models.metricas import EventoUsuario, SesionUsuario, Navegacion
from app.models.ruta import Ruta, EstadoRuta

# Zona horaria del negocio: define "qué día" y "qué hora" es cada registro.
TZ = "America/Argentina/Buenos_Aires"

_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# ── Mapa de eventos ──────────────────────────────────────────────────────────
# (método HTTP, patrón de la ruta sin /api/v1) -> (EVENTO, tipo, entidad)
# Se registran solo las operaciones que MODIFICAN datos y terminaron bien (2xx).
# La ubicación del chofer (cada 15 s) se excluye a propósito: sería ruido.
_E = [
    ("POST",   r"/clientes",                                         "CREAR_CLIENTE",        "crear",     "cliente"),
    ("PUT",    r"/clientes/{id}",                                    "EDITAR_CLIENTE",       "editar",    "cliente"),
    ("PATCH",  r"/clientes/{id}/baja",                               "ELIMINAR_CLIENTE",     "eliminar",  "cliente"),
    ("POST",   r"/entregas",                                         "CREAR_ENTREGA",        "crear",     "entrega"),
    ("PUT",    r"/entregas/{id}",                                    "EDITAR_ENTREGA",       "editar",    "entrega"),
    ("PATCH",  r"/entregas/{id}/cancelar",                           "CANCELAR_ENTREGA",     "eliminar",  "entrega"),
    ("PATCH",  r"/entregas/{id}/completar",                          "COMPLETAR_ENTREGA",    "operacion", "entrega"),
    ("POST",   r"/rutas",                                            "CREAR_RUTA",           "crear",     "ruta"),
    ("PATCH",  r"/rutas/{id}/asignar",                               "ASIGNAR_RUTA",         "operacion", "ruta"),
    ("PATCH",  r"/rutas/{id}/iniciar",                               "INICIAR_RUTA",         "operacion", "ruta"),
    ("PATCH",  r"/rutas/{id}/finalizar",                             "FINALIZAR_RUTA",       "operacion", "ruta"),
    ("PATCH",  r"/rutas/{id}/entregas/{id}/confirmar",               "CONFIRMAR_ENTREGA",    "operacion", "entrega"),
    ("PATCH",  r"/rutas/{id}/entregas/{id}/no-entregada",            "ENTREGA_NO_REALIZADA", "operacion", "entrega"),
    ("PATCH",  r"/rutas/{id}/paradas/{id}/nota",                     "NOTA_PARADA",          "editar",    "parada"),
    ("PATCH",  r"/rutas/{id}/paradas",                               "REORDENAR_PARADAS",    "editar",    "ruta"),
    ("POST",   r"/rutas/{id}/paradas/extra",                         "AGREGAR_PARADA_EXTRA", "crear",     "parada"),
    ("PATCH",  r"/rutas/{id}/paradas/{id}",                          "EDITAR_PARADA",        "editar",    "parada"),
    ("DELETE", r"/rutas/{id}/paradas/{id}",                          "ELIMINAR_PARADA",      "eliminar",  "parada"),
    ("POST",   r"/auth/usuarios",                                    "CREAR_USUARIO",        "crear",     "usuario"),
    ("PATCH",  r"/auth/usuarios/{id}/desactivar",                    "DESACTIVAR_USUARIO",   "eliminar",  "usuario"),
    ("PATCH",  r"/auth/usuarios/{id}/reactivar",                     "REACTIVAR_USUARIO",    "editar",    "usuario"),
    ("PATCH",  r"/auth/usuarios/{id}/rol",                           "CAMBIAR_ROL",          "editar",    "usuario"),
    ("PATCH",  r"/auth/me/password",                                 "CAMBIAR_PASSWORD",     "editar",    "usuario"),
    ("POST",   r"/vehiculos",                                        "CREAR_VEHICULO",       "crear",     "vehiculo"),
    ("PUT",    r"/vehiculos/{id}",                                   "EDITAR_VEHICULO",      "editar",    "vehiculo"),
    ("DELETE", r"/vehiculos/{id}",                                   "ELIMINAR_VEHICULO",    "eliminar",  "vehiculo"),
    ("POST",   r"/puntos-salida",                                    "CREAR_PUNTO_SALIDA",   "crear",     "punto_salida"),
    ("PUT",    r"/puntos-salida/{id}",                               "EDITAR_PUNTO_SALIDA",  "editar",    "punto_salida"),
    ("PATCH",  r"/puntos-salida/{id}/predeterminado",                "EDITAR_PUNTO_SALIDA",  "editar",    "punto_salida"),
    ("DELETE", r"/puntos-salida/{id}",                               "ELIMINAR_PUNTO_SALIDA","eliminar",  "punto_salida"),
]
_MAPA = [(m, re.compile("^" + p.replace("{id}", r"[^/]+") + "$"), ev, tipo, ent) for m, p, ev, tipo, ent in _E]
# Búsquedas: GET de listados con ?search=  (no se guarda el texto buscado: puede ser un nombre de cliente)
_BUSQUEDAS = {"/clientes": "cliente", "/entregas": "entrega"}
_RE_SEGUIMIENTO = re.compile(r"^/seguimiento/[^/]+$")


def clasificar(metodo: str, ruta: str, status: int, query: dict) -> Optional[dict]:
    """Devuelve qué evento corresponde a esta petición, o None si no hay que registrarla."""
    if ruta.startswith("/api/v1"):
        ruta = ruta[len("/api/v1"):]
    ruta = ruta.rstrip("/") or "/"
    if metodo == "POST" and ruta == "/auth/login" and status in (401, 403):
        return {"evento": "LOGIN_FALLIDO", "tipo": "sesion", "entidad": None, "entidad_id": None,
                "descripcion": f"Intento de ingreso rechazado (HTTP {status})"}
    if metodo == "GET" and _RE_SEGUIMIENTO.match(ruta) and status == 200:
        return {"navegacion_publica": "/seguimiento/:codigo"}
    if metodo == "GET" and ruta in _BUSQUEDAS and status == 200 and (query.get("search") or "").strip():
        return {"evento": "BUSCAR", "tipo": "busqueda", "entidad": _BUSQUEDAS[ruta], "entidad_id": None,
                "descripcion": f"Búsqueda en {_BUSQUEDAS[ruta]}s"}
    if status >= 400:
        return None
    for m, rx, ev, tipo, ent in _MAPA:
        if m == metodo and rx.match(ruta):
            ids = _UUID_RE.findall(ruta)
            # En rutas anidadas (/rutas/{ruta}/entregas/{entrega}/...) el registro afectado es el último id
            eid = ids[-1] if (ent in ("entrega", "parada") and ids) else (ids[0] if ids else None)
            info = {"evento": ev, "tipo": tipo, "entidad": ent, "entidad_id": eid,
                    "descripcion": ev.replace("_", " ").capitalize()}
            if ev in ("CONFIRMAR_ENTREGA", "ENTREGA_NO_REALIZADA") and ids:
                info["ruta_id"] = ids[0]     # para detectar si esta acción cerró la ruta
            return info
    return None


# ── User-Agent y URLs ────────────────────────────────────────────────────────
def analizar_user_agent(ua: Optional[str]) -> dict:
    """Clasifica dispositivo, navegador y sistema operativo (sin librerías externas)."""
    ua = ua or ""
    if re.search(r"iPad|Tablet", ua) or ("Android" in ua and "Mobile" not in ua):
        disp = "tablet"
    elif re.search(r"Mobi|iPhone|Android", ua):
        disp = "movil"
    else:
        disp = "escritorio"
    if "Edg/" in ua or "EdgA/" in ua:
        nav = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        nav = "Opera"
    elif "SamsungBrowser" in ua:
        nav = "Samsung Internet"
    elif "Firefox/" in ua or "FxiOS" in ua:
        nav = "Firefox"
    elif "Chrome/" in ua or "CriOS" in ua:
        nav = "Chrome"
    elif "Safari/" in ua:
        nav = "Safari"
    else:
        nav = "Otro"
    if "Windows" in ua:
        so = "Windows"
    elif "Android" in ua:
        so = "Android"
    elif re.search(r"iPhone|iPad|iOS", ua):
        so = "iOS"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        so = "macOS"
    elif "Linux" in ua:
        so = "Linux"
    else:
        so = "Otro"
    return {"dispositivo": disp, "navegador": nav, "sistema_operativo": so}


def normalizar_url(url: Optional[str]) -> Optional[str]:
    """/admin/rutas/3f2a... -> /admin/rutas/:id ; /seguimiento/AB12 -> /seguimiento/:codigo."""
    if not url:
        return None
    u = url.split("?")[0].split("#")[0].strip()
    u = _UUID_RE.sub(":id", u)
    u = re.sub(r"^/seguimiento/[^/]+", "/seguimiento/:codigo", u)
    if len(u) > 1:
        u = u.rstrip("/")
    return u[:300] or None


# ── Captura ──────────────────────────────────────────────────────────────────
def _uuid(valor) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(valor)) if valor else None
    except ValueError:
        return None


def iniciar_sesion(db: Session, usuario_id, rol: str, user_agent: Optional[str]) -> Optional[uuid.UUID]:
    """Crea la sesión y registra el LOGIN. Devuelve el id de sesión (va dentro del JWT) o None."""
    try:
        ua = analizar_user_agent(user_agent)
        sesion = SesionUsuario(usuario_id=_uuid(usuario_id), rol=rol, **ua)
        db.add(sesion)
        db.flush()
        db.add(EventoUsuario(usuario_id=sesion.usuario_id, sesion_id=sesion.id, rol=rol, evento="LOGIN",
                             tipo="sesion", descripcion=f"Ingreso desde {ua['dispositivo']} ({ua['navegador']})"))
        db.commit()
        return sesion.id
    except Exception as exc:  # la analítica no puede impedir el login
        db.rollback()
        logger.warning(f"métricas: no se pudo registrar el inicio de sesión: {exc}")
        return None


def cerrar_sesion(db: Session, usuario_id, sesion_id, rol: Optional[str]) -> None:
    try:
        sid = _uuid(sesion_id)
        ahora = datetime.now(timezone.utc)
        if sid:
            db.query(SesionUsuario).filter(SesionUsuario.id == sid, SesionUsuario.fecha_fin.is_(None)).update(
                {"fecha_fin": ahora, "ultima_actividad": ahora})
        db.add(EventoUsuario(usuario_id=_uuid(usuario_id), sesion_id=sid, rol=rol, evento="LOGOUT",
                             tipo="sesion", descripcion="Cierre de sesión"))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(f"métricas: no se pudo registrar el cierre de sesión: {exc}")


def _tocar_sesion(db: Session, sesion_id) -> None:
    sid = _uuid(sesion_id)
    if sid:
        db.query(SesionUsuario).filter(SesionUsuario.id == sid, SesionUsuario.fecha_fin.is_(None)).update(
            {"ultima_actividad": datetime.now(timezone.utc)})


def registrar_navegacion(db: Session, usuario_id, sesion_id, url: str, url_anterior: Optional[str],
                         user_agent: Optional[str]) -> None:
    try:
        url_n = normalizar_url(url)
        if not url_n:
            return
        ua = analizar_user_agent(user_agent)
        db.add(Navegacion(usuario_id=_uuid(usuario_id), sesion_id=_uuid(sesion_id), url=url_n,
                          url_anterior=normalizar_url(url_anterior), dispositivo=ua["dispositivo"],
                          navegador=ua["navegador"]))
        _tocar_sesion(db, sesion_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(f"métricas: no se pudo registrar la navegación: {exc}")


def registrar_peticion(db: Session, info: dict, payload: Optional[dict], status: int, duracion_ms: int,
                       user_agent: Optional[str]) -> None:
    """Guarda lo que el middleware clasificó (evento de negocio, login fallido o visita pública)."""
    try:
        if "navegacion_publica" in info:
            ua = analizar_user_agent(user_agent)
            db.add(Navegacion(usuario_id=None, url=info["navegacion_publica"], dispositivo=ua["dispositivo"],
                              navegador=ua["navegador"]))
        else:
            payload = payload or {}
            db.add(EventoUsuario(
                usuario_id=_uuid(payload.get("sub")), sesion_id=_uuid(payload.get("sid")), rol=payload.get("rol"),
                evento=info["evento"], tipo=info["tipo"], entidad=info["entidad"], entidad_id=info["entidad_id"],
                descripcion=info["descripcion"], http_status=status, duracion_ms=duracion_ms))
            _tocar_sesion(db, payload.get("sid"))
            # La ruta se cierra sola al resolver su última entrega: se deja constancia como evento propio
            if info.get("ruta_id"):
                ruta = db.get(Ruta, _uuid(info["ruta_id"]))
                if ruta is not None and ruta.estado in (EstadoRuta.completada, EstadoRuta.finalizada):
                    db.add(EventoUsuario(
                        usuario_id=_uuid(payload.get("sub")), sesion_id=_uuid(payload.get("sid")), rol=payload.get("rol"),
                        evento="RUTA_CERRADA", tipo="operacion", entidad="ruta", entidad_id=info["ruta_id"],
                        descripcion=f"Ruta cerrada automáticamente ({ruta.estado.value})"))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(f"métricas: no se pudo registrar la petición: {exc}")


# ── Consultas de análisis ────────────────────────────────────────────────────
# Rango [ini, fin): el día se calcula en hora argentina, no en UTC.
_RANGO = "fecha >= (CAST(:desde AS timestamp) AT TIME ZONE :tz) AND fecha < (CAST(:hasta_mas_uno AS timestamp) AT TIME ZONE :tz)"

_RANGO_S = "fecha_inicio >= (CAST(:desde AS timestamp) AT TIME ZONE :tz) AND fecha_inicio < (CAST(:hasta_mas_uno AS timestamp) AT TIME ZONE :tz)"
SQL_EVENTOS = f"SELECT evento, tipo, count(*) AS n FROM eventos_usuario WHERE {_RANGO} GROUP BY evento, tipo ORDER BY n DESC"
SQL_SESIONES = """
SELECT count(*) AS sesiones,
       count(DISTINCT usuario_id) AS usuarios_activos,
       COALESCE(avg(EXTRACT(EPOCH FROM (COALESCE(fecha_fin, ultima_actividad) - fecha_inicio))) / 60, 0) AS duracion_prom_min,
       COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (COALESCE(fecha_fin, ultima_actividad) - fecha_inicio))) / 60, 0) AS duracion_mediana_min
FROM sesiones_usuario
WHERE fecha_inicio >= (CAST(:desde AS timestamp) AT TIME ZONE :tz) AND fecha_inicio < (CAST(:hasta_mas_uno AS timestamp) AT TIME ZONE :tz)
"""
SQL_POR_ROL = f"""
SELECT COALESCE(rol, 'desconocido') AS rol, count(*) AS sesiones, count(DISTINCT usuario_id) AS usuarios,
       round(avg(EXTRACT(EPOCH FROM (COALESCE(fecha_fin, ultima_actividad) - fecha_inicio))) / 60)::int AS duracion_prom_min
FROM sesiones_usuario WHERE {_RANGO_S} GROUP BY 1 ORDER BY sesiones DESC
"""
SQL_URLS = f"SELECT url, count(*) AS visitas FROM navegacion WHERE {_RANGO} GROUP BY url ORDER BY visitas DESC LIMIT 300"
SQL_HEATMAP = f"""
SELECT EXTRACT(ISODOW FROM f)::int AS dia, EXTRACT(HOUR FROM f)::int AS hora, count(*) AS n
FROM (SELECT fecha AT TIME ZONE :tz AS f FROM navegacion WHERE {_RANGO}) t GROUP BY 1, 2
"""
SQL_DISPOSITIVOS = f"SELECT COALESCE(dispositivo, 'desconocido') AS nombre, count(*) AS n FROM sesiones_usuario WHERE {_RANGO_S} GROUP BY 1 ORDER BY n DESC"
SQL_NAVEGADORES = f"SELECT COALESCE(navegador, 'desconocido') AS nombre, count(*) AS n FROM sesiones_usuario WHERE {_RANGO_S} GROUP BY 1 ORDER BY n DESC"
SQL_SERIE = """
SELECT d::date AS fecha,
  (SELECT count(*) FROM sesiones_usuario s WHERE (s.fecha_inicio AT TIME ZONE :tz)::date = d::date) AS sesiones,
  (SELECT count(*) FROM navegacion n WHERE (n.fecha AT TIME ZONE :tz)::date = d::date) AS visitas,
  (SELECT count(*) FROM eventos_usuario e WHERE (e.fecha AT TIME ZONE :tz)::date = d::date
        AND e.tipo IN ('crear', 'editar', 'eliminar', 'operacion')) AS operaciones
FROM generate_series(CAST(:desde AS date), CAST(:hasta AS date), interval '1 day') d ORDER BY 1
"""
SQL_FLUJO = f"""
SELECT url_anterior AS desde, url AS hacia, count(*) AS n FROM navegacion
WHERE url_anterior IS NOT NULL AND url_anterior <> url AND {_RANGO} GROUP BY 1, 2 ORDER BY n DESC LIMIT 10
"""
SQL_LENTAS = f"""
SELECT evento, count(*) AS n, round(avg(duracion_ms))::int AS promedio_ms,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY duracion_ms))::int AS p95_ms
FROM eventos_usuario WHERE duracion_ms IS NOT NULL AND {_RANGO} GROUP BY evento ORDER BY p95_ms DESC LIMIT 8
"""

# Secciones de la aplicación, para detectar funcionalidades poco usadas.
SECCIONES = [
    ("Panel principal", "/admin", True), ("Clientes", "/admin/clientes", False), ("Entregas", "/admin/entregas", False),
    ("Choferes", "/admin/usuarios", False), ("Rutas", "/admin/rutas", False), ("Flota", "/admin/flota", False),
    ("Plantillas", "/admin/plantillas", False), ("Vista del chofer", "/chofer", False),
    ("Seguimiento público", "/seguimiento", False),
]
# Formularios de alta: pantalla de inicio -> evento que indica que se completó.
FLUJOS = [
    ("Nuevo cliente", "/admin/clientes/nuevo", "CREAR_CLIENTE"),
    ("Nueva entrega", "/admin/entregas/nueva", "CREAR_ENTREGA"),
    ("Nueva ruta", "/admin/rutas/nueva", "CREAR_RUTA"),
]


def _pct(parte: float, total: float) -> float:
    return round(100.0 * parte / total, 1) if total else 0.0


def tablero(db: Session, desde: Optional[date] = None, hasta: Optional[date] = None) -> dict:
    """Arma todos los indicadores del dashboard para el rango [desde, hasta] (ambos inclusive)."""
    hoy = db.execute(text("SELECT (now() AT TIME ZONE :tz)::date"), {"tz": TZ}).scalar()
    hasta = hasta or hoy
    desde = desde or (hasta - timedelta(days=29))
    p = {"desde": desde, "hasta": hasta, "hasta_mas_uno": hasta + timedelta(days=1), "tz": TZ}

    eventos = [dict(r._mapping) for r in db.execute(text(SQL_EVENTOS), p)]
    por_evento = {e["evento"]: e["n"] for e in eventos}
    por_tipo: dict = {}
    for e in eventos:
        por_tipo[e["tipo"]] = por_tipo.get(e["tipo"], 0) + e["n"]
    ses = dict(db.execute(text(SQL_SESIONES), p).one()._mapping)
    urls = [dict(r._mapping) for r in db.execute(text(SQL_URLS), p)]
    visitas = sum(u["visitas"] for u in urls)
    visitas_url = {u["url"]: u["visitas"] for u in urls}

    operaciones = sum(por_tipo.get(t, 0) for t in ("crear", "editar", "eliminar", "operacion"))
    entregas_creadas = por_evento.get("CREAR_ENTREGA", 0)
    confirmadas = por_evento.get("CONFIRMAR_ENTREGA", 0)
    no_realizadas = por_evento.get("ENTREGA_NO_REALIZADA", 0)
    sesiones = ses["sesiones"] or 0

    kpis = {
        "visitas": visitas,
        "sesiones": sesiones,
        "usuarios_activos": ses["usuarios_activos"] or 0,
        "logins": por_evento.get("LOGIN", 0),
        "logins_fallidos": por_evento.get("LOGIN_FALLIDO", 0),
        "duracion_promedio_min": round(float(ses["duracion_prom_min"]), 1),
        "duracion_mediana_min": round(float(ses["duracion_mediana_min"]), 1),
        "operaciones": operaciones,
        "operaciones_por_sesion": round(operaciones / sesiones, 1) if sesiones else 0,
        "registros_creados": por_tipo.get("crear", 0),
        "registros_modificados": por_tipo.get("editar", 0),
        "registros_eliminados": por_tipo.get("eliminar", 0),
        "busquedas": por_tipo.get("busqueda", 0),
        "entregas_creadas": entregas_creadas,
        "entregas_confirmadas": confirmadas,
        "entregas_no_realizadas": no_realizadas,
        "conversion_entregas_pct": _pct(confirmadas, entregas_creadas),
        "tasa_no_entrega_pct": _pct(no_realizadas, confirmadas + no_realizadas),
        "rutas_creadas": por_evento.get("CREAR_RUTA", 0),
        # cierre automático (al resolver la última entrega) + cierre manual por el chofer
        "rutas_cerradas": por_evento.get("RUTA_CERRADA", 0) + por_evento.get("FINALIZAR_RUTA", 0),
    }

    flujos = []
    for nombre, url, evento in FLUJOS:
        inicios, hechos = visitas_url.get(url, 0), por_evento.get(evento, 0)
        flujos.append({"flujo": nombre, "inicios": inicios, "completados": min(hechos, inicios) if inicios else hechos,
                       "abandono_pct": round(max(0.0, 100.0 - _pct(hechos, inicios)), 1) if inicios else 0.0})
    total_inicios = sum(f["inicios"] for f in flujos)
    total_ok = sum(f["completados"] for f in flujos)
    kpis["abandono_formularios_pct"] = round(100.0 - _pct(total_ok, total_inicios), 1) if total_inicios else 0.0

    uso = []
    for nombre, prefijo, exacto in SECCIONES:
        n = sum(v for u, v in visitas_url.items() if (u == prefijo if exacto else (u == prefijo or u.startswith(prefijo + "/"))))
        uso.append({"seccion": nombre, "visitas": n})

    heat = [[0] * 24 for _ in range(7)]
    for r in db.execute(text(SQL_HEATMAP), p):
        heat[r.dia - 1][r.hora] = r.n

    embudo_rutas = [("Creadas", ["CREAR_RUTA"]), ("Asignadas", ["ASIGNAR_RUTA"]),
                    ("Iniciadas", ["INICIAR_RUTA"]), ("Cerradas", ["RUTA_CERRADA", "FINALIZAR_RUTA"])]
    return {
        "desde": str(desde), "hasta": str(hasta), "zona_horaria": TZ,
        "kpis": kpis,
        "top_urls": urls[:10],
        "uso_por_seccion": sorted(uso, key=lambda x: x["visitas"]),
        "mapa_calor": heat,
        "sesiones_por_rol": [dict(r._mapping) for r in db.execute(text(SQL_POR_ROL), p)],
        "dispositivos": [dict(r._mapping) for r in db.execute(text(SQL_DISPOSITIVOS), p)],
        "navegadores": [dict(r._mapping) for r in db.execute(text(SQL_NAVEGADORES), p)],
        "serie_diaria": [{"fecha": str(r.fecha), "sesiones": r.sesiones, "visitas": r.visitas, "operaciones": r.operaciones}
                         for r in db.execute(text(SQL_SERIE), p)],
        "eventos": eventos[:12],
        "flujo_navegacion": [dict(r._mapping) for r in db.execute(text(SQL_FLUJO), p)],
        "operaciones_lentas": [dict(r._mapping) for r in db.execute(text(SQL_LENTAS), p)],
        "abandono_formularios": flujos,
        "embudo_rutas": [{"etapa": e, "cantidad": sum(por_evento.get(x, 0) for x in evs)} for e, evs in embudo_rutas],
        "embudo_entregas": [{"etapa": "Creadas", "cantidad": entregas_creadas},
                            {"etapa": "Confirmadas", "cantidad": confirmadas},
                            {"etapa": "No realizadas", "cantidad": no_realizadas}],
    }
