# -*- coding: utf-8 -*-
"""Quién puede hacer qué: el chofer solo opera sobre SUS rutas; el administrador sobre todo."""
import uuid
import pytest

API = "/api/v1"


def test_sin_token_todo_devuelve_401(client):
    for metodo, url in [("get", "/rutas"), ("get", "/entregas"), ("get", "/clientes"),
                        ("get", "/auth/usuarios"), ("post", "/rutas"), ("get", "/puntos-salida")]:
        assert getattr(client, metodo)(API + url).status_code == 401, url


def test_chofer_no_puede_usar_endpoints_de_admin(client, fab, chofer_a):
    h = chofer_a["headers"]
    ruta = fab.ruta(chofer=chofer_a)
    parada = ruta["paradas"][0]
    intentos = [
        ("post", "/rutas", {"nombre": "x", "entregas_ids": [str(uuid.uuid4())], "origen_latitud": -34.6, "origen_longitud": -58.4}),
        ("patch", f"/rutas/{ruta['id']}/asignar", {"chofer_id": chofer_a["id"]}),
        ("patch", f"/rutas/{ruta['id']}/paradas", {"paradas": []}),
        ("post", f"/rutas/{ruta['id']}/paradas/extra", {"descripcion": "Nafta"}),
        ("delete", f"/rutas/{ruta['id']}/paradas/{parada['id']}", None),
        ("post", "/clientes", {"nombre": "x"}),
        ("put", f"/clientes/{uuid.uuid4()}", {"nombre": "x"}),
        ("patch", f"/clientes/{uuid.uuid4()}/baja", None),
        ("post", "/entregas", {}),
        ("put", f"/entregas/{parada['entrega_id']}", {"descripcion": "x"}),
        ("patch", f"/entregas/{parada['entrega_id']}/cancelar", None),
        ("patch", f"/entregas/{parada['entrega_id']}/completar", None),
        ("get", "/auth/usuarios", None),
        ("get", "/puntos-salida", None),
        ("post", "/auth/usuarios", {"nombre": "x"}),
        ("patch", f"/auth/usuarios/{uuid.uuid4()}/desactivar", None),
        ("patch", f"/auth/usuarios/{uuid.uuid4()}/rol", {"rol": "admin"}),
        ("post", "/puntos-salida", {"nombre": "x", "descripcion": "y"}),
    ]
    for metodo, url, body in intentos:
        r = getattr(client, metodo)(API + url, headers=h, **({"json": body} if body is not None else {}))
        assert r.status_code == 403, f"{metodo.upper()} {url} -> {r.status_code}"


def test_chofer_no_toca_rutas_de_otro_chofer(client, fab, chofer_a, chofer_b):
    ruta = fab.ruta_en_curso(chofer_a)
    rid = ruta["id"]
    eid = ruta["paradas"][0]["entrega_id"]
    hb = chofer_b["headers"]
    assert client.get(f"{API}/rutas/{rid}", headers=hb).status_code == 403
    assert client.patch(f"{API}/rutas/{rid}/iniciar", headers=hb).status_code == 403
    assert client.patch(f"{API}/rutas/{rid}/finalizar", headers=hb).status_code == 403
    assert client.patch(f"{API}/rutas/{rid}/ubicacion", headers=hb,
                        json={"latitud": -34.6, "longitud": -58.4}).status_code == 403
    assert client.patch(f"{API}/rutas/{rid}/entregas/{eid}/confirmar", headers=hb,
                        json={"codigo": "ABCD1234"}).status_code == 403


def test_chofer_solo_ve_sus_rutas_y_entregas(client, fab, chofer_a, chofer_b):
    ruta_a = fab.ruta(chofer=chofer_a)
    ruta_b = fab.ruta(chofer=chofer_b)
    fab.ruta()  # una ruta sin chofer
    ids_a = {r["id"] for r in client.get(f"{API}/rutas", headers=chofer_a["headers"]).json()["rutas"]}
    assert ids_a == {ruta_a["id"]}
    entregas_a = client.get(f"{API}/entregas", headers=chofer_a["headers"]).json()["entregas"]
    assert {e["id"] for e in entregas_a} == {p["entrega_id"] for p in ruta_a["paradas"]}
    # Entrega ajena: 404 (no 403), para no revelar que existe
    ajena = ruta_b["paradas"][0]["entrega_id"]
    assert client.get(f"{API}/entregas/{ajena}", headers=chofer_a["headers"]).status_code == 404


def test_chofer_no_ve_el_codigo_de_confirmacion(client, fab, chofer_a, admin):
    ruta = fab.ruta(chofer=chofer_a)
    eid = ruta["paradas"][0]["entrega_id"]
    como_chofer = client.get(f"{API}/entregas/{eid}", headers=chofer_a["headers"]).json()
    como_admin = client.get(f"{API}/entregas/{eid}", headers=admin["headers"]).json()
    assert not como_chofer.get("codigo_confirmacion")
    assert como_admin.get("codigo_confirmacion")


def test_chofer_no_puede_ser_asignado_si_esta_inactivo_o_es_admin(client, fab, admin2):
    ruta = fab.ruta()
    r = client.patch(f"{API}/rutas/{ruta['id']}/asignar", headers=fab.h, json={"chofer_id": admin2["id"]})
    assert r.status_code in (400, 404)


def test_seguimiento_publico_no_expone_datos_internos(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    r = client.get(f"{API}/seguimiento/{ruta['codigo_seguimiento']}")
    assert r.status_code == 200
    texto = r.text.lower()
    for prohibido in ("codigo_confirmacion", "password", "email", "telefono", ruta["id"]):
        assert prohibido not in texto, prohibido
    assert client.get(f"{API}/seguimiento/{uuid.uuid4().hex[:10]}").status_code == 404
