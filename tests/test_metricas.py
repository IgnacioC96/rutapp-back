# -*- coding: utf-8 -*-
"""Métricas de uso: captura de sesiones, eventos y navegación, y tablero de análisis."""
from sqlalchemy.orm import sessionmaker

from app.core.security import verificar_token
from app.db.database import engine
from app.models.metricas import EventoUsuario, Navegacion, SesionUsuario
from app.services import metricas
from app.services.metricas import analizar_user_agent, clasificar, normalizar_url

API = "/api/v1"
Sesion = sessionmaker(bind=engine)
UA_CHROME_PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
UA_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"


def _eventos(**filtro):
    with Sesion() as db:
        return db.query(EventoUsuario).filter_by(**filtro).all()


def _login(client, email, clave, rol, ua=UA_CHROME_PC):
    return client.post(f"{API}/auth/login", json={"email": email, "password": clave, "rol": rol},
                       headers={"User-Agent": ua})


def _usuario_real(client, admin, rol="chofer"):
    email = f"{rol}.metricas@test.com"
    r = client.post(f"{API}/auth/usuarios", headers=admin["headers"], json={
        "nombre": "Usuario Métricas", "email": email, "password": "Clave-Segura-123", "rol": rol})
    assert r.status_code == 201, r.text
    return email, "Clave-Segura-123"


# ── Funciones puras ──────────────────────────────────────────────────────────
def test_normalizar_url_reemplaza_ids_y_codigos():
    assert normalizar_url("/admin/rutas/3f2a1b4c-0d11-4e22-9a33-123456789abc?x=1") == "/admin/rutas/:id"
    assert normalizar_url("/seguimiento/ABCD1234/") == "/seguimiento/:codigo"
    assert normalizar_url("/admin/") == "/admin"
    assert normalizar_url("") is None


def test_analizar_user_agent():
    assert analizar_user_agent(UA_CHROME_PC) == {"dispositivo": "escritorio", "navegador": "Chrome", "sistema_operativo": "Windows"}
    assert analizar_user_agent(UA_IPHONE) == {"dispositivo": "movil", "navegador": "Safari", "sistema_operativo": "iOS"}
    assert analizar_user_agent(None)["dispositivo"] == "escritorio"


def test_clasificar_solo_registra_lo_que_modifica_datos():
    assert clasificar("POST", "/api/v1/entregas", 201, {})["evento"] == "CREAR_ENTREGA"
    assert clasificar("POST", "/api/v1/entregas", 422, {}) is None            # falló: no se registra
    assert clasificar("GET", "/api/v1/entregas", 200, {}) is None             # lectura sin búsqueda
    assert clasificar("GET", "/api/v1/entregas", 200, {"search": "x"})["evento"] == "BUSCAR"
    assert clasificar("PATCH", "/api/v1/rutas/abc/ubicacion", 200, {}) is None  # cada 15 s: ruido
    assert clasificar("PATCH", "/api/v1/rutas/1/entregas/2/confirmar", 200, {})["evento"] == "CONFIRMAR_ENTREGA"


# ── Sesiones ─────────────────────────────────────────────────────────────────
def test_login_crea_sesion_y_evento_y_el_token_lleva_el_sid(client, admin):
    email, clave = _usuario_real(client, admin)
    r = _login(client, email, clave, "chofer", UA_IPHONE)
    assert r.status_code == 200
    sid = verificar_token(r.json()["access_token"])["sid"]
    with Sesion() as db:
        s = db.get(SesionUsuario, sid)
        assert s.dispositivo == "movil" and s.navegador == "Safari" and s.rol == "chofer"
    assert len(_eventos(evento="LOGIN")) == 1


def test_login_fallido_se_registra_sin_usuario(client, admin):
    email, _ = _usuario_real(client, admin)
    assert _login(client, email, "incorrecta", "chofer").status_code == 401
    ev = _eventos(evento="LOGIN_FALLIDO")
    assert len(ev) == 1 and ev[0].usuario_id is None
    assert email not in (ev[0].descripcion or "")          # no se guarda el email tipeado


def test_cerrar_sesion_completa_fecha_fin_y_registra_logout(client, admin):
    email, clave = _usuario_real(client, admin)
    token = _login(client, email, clave, "chofer").json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.post(f"{API}/metricas/sesion/cerrar", headers=h).status_code == 204
    with Sesion() as db:
        s = db.query(SesionUsuario).filter_by(rol="chofer").one()
        assert s.fecha_fin is not None
    assert len(_eventos(evento="LOGOUT")) == 1


# ── Eventos y navegación ─────────────────────────────────────────────────────
def test_las_operaciones_exitosas_quedan_registradas_con_tiempo_y_sesion(client, admin):
    email, clave = _usuario_real(client, admin, "admin")
    h = {"Authorization": "Bearer " + _login(client, email, clave, "admin").json()["access_token"]}
    r = client.post(f"{API}/clientes", headers=h, json={"nombre": "Cliente M", "telefono_whatsapp": "11 5000-0001",
                    "direcciones": [{"descripcion": "Calle 1", "es_principal": True, "latitud": -34.6, "longitud": -58.5}]})
    assert r.status_code == 201
    ev = _eventos(evento="CREAR_CLIENTE")
    assert len(ev) == 1
    assert ev[0].tipo == "crear" and ev[0].entidad == "cliente" and ev[0].http_status == 201
    assert ev[0].duracion_ms is not None and ev[0].sesion_id is not None


def test_una_operacion_rechazada_no_genera_evento(client, admin):
    r = client.post(f"{API}/clientes", headers=admin["headers"], json={"nombre": ""})
    assert r.status_code == 422
    assert _eventos(evento="CREAR_CLIENTE") == []


def test_la_busqueda_se_registra_sin_guardar_el_texto(client, admin):
    client.get(f"{API}/clientes?search=Juan+Perez", headers=admin["headers"])
    ev = _eventos(evento="BUSCAR")
    assert len(ev) == 1 and "Juan" not in (ev[0].descripcion or "")


def test_navegacion_normaliza_y_exige_sesion_iniciada(client, admin):
    assert client.post(f"{API}/metricas/navegacion", json={"url": "/admin"}).status_code == 401
    r = client.post(f"{API}/metricas/navegacion", headers=admin["headers"],
                    json={"url": "/admin/rutas/3f2a1b4c-0d11-4e22-9a33-123456789abc", "url_anterior": "/admin"})
    assert r.status_code == 204
    with Sesion() as db:
        n = db.query(Navegacion).one()
        assert n.url == "/admin/rutas/:id" and n.url_anterior == "/admin"


def test_visita_publica_al_seguimiento_se_registra_sin_usuario(client, admin, fab, chofer_a):
    ruta = fab.ruta(chofer=chofer_a, cantidad=1)
    codigo = ruta["codigo_seguimiento"]
    assert client.get(f"{API}/seguimiento/{codigo}").status_code == 200
    with Sesion() as db:
        n = db.query(Navegacion).filter_by(url="/seguimiento/:codigo").one()
        assert n.usuario_id is None


def test_si_la_analitica_falla_la_aplicacion_sigue_funcionando(client, admin, monkeypatch):
    def roto(*a, **k):
        raise RuntimeError("falla simulada")
    monkeypatch.setattr(metricas, "registrar_peticion", roto)
    r = client.post(f"{API}/clientes", headers=admin["headers"], json={"nombre": "Sigue OK", "telefono_whatsapp": "11 5000-0002",
                    "direcciones": [{"descripcion": "Calle 2", "es_principal": True, "latitud": -34.6, "longitud": -58.5}]})
    assert r.status_code == 201


# ── Tablero ──────────────────────────────────────────────────────────────────
def test_el_tablero_es_solo_para_administradores(client, admin, chofer_a):
    assert client.get(f"{API}/metricas/dashboard", headers=chofer_a["headers"]).status_code == 403
    assert client.get(f"{API}/metricas/dashboard").status_code == 401
    assert client.get(f"{API}/metricas/dashboard", headers=admin["headers"]).status_code == 200


def test_el_tablero_calcula_los_indicadores(client, admin, fab, chofer_a):
    ruta = fab.ruta(chofer=chofer_a, cantidad=2)
    client.patch(f"{API}/rutas/{ruta['id']}/iniciar", headers=chofer_a["headers"])
    client.post(f"{API}/metricas/navegacion", headers=admin["headers"], json={"url": "/admin/rutas/nueva", "url_anterior": "/admin"})
    d = client.get(f"{API}/metricas/dashboard", headers=admin["headers"]).json()
    k = d["kpis"]
    assert k["entregas_creadas"] == 2 and k["rutas_creadas"] == 1
    assert k["registros_creados"] >= 4          # 2 clientes + 2 entregas + 1 ruta
    assert k["visitas"] == 1
    assert d["top_urls"][0]["url"] == "/admin/rutas/nueva"
    assert len(d["mapa_calor"]) == 7 and len(d["mapa_calor"][0]) == 24
    assert len(d["serie_diaria"]) == 30
    flujo = {f["flujo"]: f for f in d["abandono_formularios"]}
    assert flujo["Nueva ruta"]["inicios"] == 1 and flujo["Nueva ruta"]["abandono_pct"] == 0.0


def test_al_resolver_la_ultima_entrega_se_registra_el_cierre_automatico_de_la_ruta(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a, cantidad=2)
    p1, p2 = ruta["paradas"]
    cod = lambda eid: client.get(f"{API}/entregas/{eid}", headers=fab.h).json()["codigo_confirmacion"]
    client.patch(f"{API}/rutas/{ruta['id']}/entregas/{p1['entrega_id']}/confirmar", headers=chofer_a["headers"],
                 json={"codigo": cod(p1["entrega_id"])})
    assert _eventos(evento="RUTA_CERRADA") == []          # todavía falta una parada
    client.patch(f"{API}/rutas/{ruta['id']}/entregas/{p2['entrega_id']}/no-entregada", headers=chofer_a["headers"], json={})
    cierres = _eventos(evento="RUTA_CERRADA")
    assert len(cierres) == 1 and cierres[0].entidad_id == ruta["id"]
    assert len(_eventos(evento="CONFIRMAR_ENTREGA")) == 1 and len(_eventos(evento="ENTREGA_NO_REALIZADA")) == 1
    k = client.get(f"{API}/metricas/dashboard", headers=fab.h).json()["kpis"]
    assert k["rutas_cerradas"] == 1 and k["tasa_no_entrega_pct"] == 50.0
