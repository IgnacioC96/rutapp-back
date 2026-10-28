# -*- coding: utf-8 -*-
"""Una misma entrega nunca puede quedar en dos rutas, aunque dos administradores planifiquen a la vez."""
import threading
from sqlalchemy import text

from app.api.routes import rutas as rutas_routes
from tests.conftest import Sesion

API = "/api/v1"


def _body(ids, nombre="Ruta"):
    return {"nombre": nombre, "entregas_ids": ids, "origen_latitud": -34.61, "origen_longitud": -58.40}


def test_entrega_ya_tomada_no_entra_en_otra_ruta(client, fab, admin2):
    eid = fab.entrega()[0]
    assert client.post(f"{API}/rutas", headers=fab.h, json=_body([eid])).status_code == 201
    r = client.post(f"{API}/rutas", headers=admin2["headers"], json=_body([eid], "Otra"))
    assert r.status_code == 400


def test_carrera_otro_admin_toma_la_entrega_mientras_se_optimiza(client, fab, admin2, monkeypatch):
    """
    Reproduce la carrera real: la ruta A valida que la entrega está pendiente y se pone a
    optimizar (varios segundos con ORS). Mientras tanto la ruta B la toma. Al volver, A debe
    detectar el conflicto (409) y NO crear la ruta ni duplicar la entrega.
    """
    eid = fab.entrega()[0]
    original = rutas_routes.optimizar_ruta

    async def optimizar_y_colarse(origen, coords, retorno=None):
        # "otro administrador" crea su ruta con la misma entrega en este instante
        with Sesion() as db:
            db.execute(text("UPDATE entregas SET estado = 'en_curso' WHERE id = :i"), {"i": eid})
            db.commit()
        return await original(origen, coords, retorno)

    monkeypatch.setattr(rutas_routes, "optimizar_ruta", optimizar_y_colarse)
    r = client.post(f"{API}/rutas", headers=fab.h, json=_body([eid]))
    assert r.status_code == 409, r.text
    assert "otra ruta" in r.text
    with Sesion() as db:
        assert db.execute(text("SELECT count(*) FROM rutas")).scalar() == 0
        assert db.execute(text("SELECT count(*) FROM paradas_ruta")).scalar() == 0


def test_dos_solicitudes_simultaneas_solo_una_gana(client, fab, admin2):
    eid = fab.entrega()[0]
    resultados = []

    def crear(headers, nombre):
        resultados.append(client.post(f"{API}/rutas", headers=headers, json=_body([eid], nombre)).status_code)

    hilos = [threading.Thread(target=crear, args=(fab.h, "A")),
             threading.Thread(target=crear, args=(admin2["headers"], "B"))]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(resultados)[0] == 201 and 201 not in sorted(resultados)[1:], resultados
    with Sesion() as db:
        assert db.execute(text("SELECT count(*) FROM paradas_ruta WHERE entrega_id = :i"), {"i": eid}).scalar() == 1


def test_no_se_puede_cancelar_una_entrega_que_ya_esta_en_una_ruta(client, fab):
    eid = fab.entrega()[0]
    client.post(f"{API}/rutas", headers=fab.h, json=_body([eid]))
    assert client.patch(f"{API}/entregas/{eid}/cancelar", headers=fab.h).status_code == 400


def test_no_se_reasigna_una_ruta_ya_asignada(client, fab, chofer_a, chofer_b):
    ruta = fab.ruta(chofer=chofer_a)
    r = client.patch(f"{API}/rutas/{ruta['id']}/asignar", headers=fab.h, json={"chofer_id": chofer_b["id"]})
    assert r.status_code == 400


def test_confirmar_dos_veces_la_misma_entrega_falla_la_segunda(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    eid = ruta["paradas"][0]["entrega_id"]
    codigo = client.get(f"{API}/entregas/{eid}", headers=fab.h).json()["codigo_confirmacion"]
    url = f"{API}/rutas/{ruta['id']}/entregas/{eid}/confirmar"
    assert client.patch(url, headers=chofer_a["headers"], json={"codigo": codigo}).status_code == 200
    assert client.patch(url, headers=chofer_a["headers"], json={"codigo": codigo}).status_code == 400
