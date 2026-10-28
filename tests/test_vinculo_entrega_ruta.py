# -*- coding: utf-8 -*-
"""Cada entrega queda vinculada a su ruta actual (de ahí sale qué entregas ve cada chofer)."""
API = "/api/v1"


def test_la_entrega_queda_vinculada_a_la_ruta(client, fab):
    ruta = fab.ruta(cantidad=2)
    for p in ruta["paradas"]:
        e = client.get(f"{API}/entregas/{p['entrega_id']}", headers=fab.h).json()
        assert e["ruta_id"] == ruta["id"]


def test_el_chofer_puede_ver_el_detalle_de_su_entrega(client, fab, chofer_a):
    ruta = fab.ruta(chofer=chofer_a)
    eid = ruta["paradas"][0]["entrega_id"]
    r = client.get(f"{API}/entregas/{eid}", headers=chofer_a["headers"])
    assert r.status_code == 200
    assert r.json()["id"] == eid


def test_finalizar_con_pendientes_libera_las_entregas(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    r = client.patch(f"{API}/rutas/{ruta['id']}/finalizar", headers=chofer_a["headers"])
    assert r.status_code == 200 and r.json()["estado"] == "finalizada"
    for p in ruta["paradas"]:
        e = client.get(f"{API}/entregas/{p['entrega_id']}", headers=fab.h).json()
        assert e["estado"] == "pendiente" and e["ruta_id"] is None
    # y se pueden volver a planificar en otra ruta
    fab.ruta(ids=[p["entrega_id"] for p in ruta["paradas"]])
