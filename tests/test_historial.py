# -*- coding: utf-8 -*-
"""Parche 3: historial de rutas con el teléfono del cliente y filtros por estado y fechas."""
API = "/api/v1"


def _codigo(client, h, eid):
    return client.get(f"{API}/entregas/{eid}", headers=h).json()["codigo_confirmacion"]


def test_las_paradas_traen_el_telefono_del_cliente(client, fab, chofer_a):
    ruta = fab.ruta(chofer=chofer_a, cantidad=2)
    for p in ruta["paradas"]:
        assert p["cliente_telefono"] and p["cliente_telefono"].startswith("+54")


def test_el_chofer_asignado_ve_el_telefono_y_otro_chofer_no_ve_la_ruta(client, fab, chofer_a, chofer_b):
    ruta = fab.ruta(chofer=chofer_a, cantidad=1)
    r = client.get(f"{API}/rutas/{ruta['id']}", headers=chofer_a["headers"])
    assert r.status_code == 200 and r.json()["paradas"][0]["cliente_telefono"]
    assert client.get(f"{API}/rutas/{ruta['id']}", headers=chofer_b["headers"]).status_code == 403
    assert client.get(f"{API}/rutas", headers=chofer_b["headers"]).json()["rutas"] == []


def test_la_entrega_trae_el_telefono_del_cliente(client, fab):
    eid = fab.entrega()[0]
    assert client.get(f"{API}/entregas/{eid}", headers=fab.h).json()["cliente_telefono"].startswith("+54")


def test_el_seguimiento_publico_no_expone_telefonos(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a, cantidad=1)
    pub = client.get(f"{API}/seguimiento/{ruta['codigo_seguimiento']}")
    assert "cliente_telefono" not in pub.text and "+54" not in pub.text


def test_resumen_de_paradas_para_el_historial(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a, cantidad=3)
    p1, p2, _ = ruta["paradas"]
    client.patch(f"{API}/rutas/{ruta['id']}/entregas/{p1['entrega_id']}/confirmar", headers=chofer_a["headers"],
                 json={"codigo": _codigo(client, fab.h, p1["entrega_id"])})
    client.patch(f"{API}/rutas/{ruta['id']}/entregas/{p2['entrega_id']}/no-entregada", headers=chofer_a["headers"], json={})
    r = client.get(f"{API}/rutas/{ruta['id']}", headers=fab.h).json()
    assert (r["paradas_total"], r["paradas_completadas"], r["paradas_omitidas"]) == (3, 1, 1)


def test_filtrar_el_historial_por_estado(client, fab, chofer_a):
    fab.ruta(cantidad=1)                      # pendiente
    en_curso = fab.ruta_en_curso(chofer_a, cantidad=1)
    r = client.get(f"{API}/rutas", headers=fab.h, params={"estado": "en_curso"}).json()
    assert [x["id"] for x in r["rutas"]] == [en_curso["id"]]
    assert client.get(f"{API}/rutas", headers=fab.h, params={"estado": "inventado"}).status_code == 422


def test_filtrar_por_rango_de_fechas(client, fab):
    a = fab.ruta(cantidad=1, fecha_programada="2026-10-01")
    b = fab.ruta(cantidad=1, fecha_programada="2026-11-10")
    ids = lambda **p: {x["id"] for x in client.get(f"{API}/rutas", headers=fab.h, params=p).json()["rutas"]}
    assert ids(fecha_desde="2026-10-15") == {b["id"]}
    assert ids(fecha_hasta="2026-10-15") == {a["id"]}
    assert ids(fecha_desde="2026-10-01", fecha_hasta="2026-11-10") == {a["id"], b["id"]}
    r = client.get(f"{API}/rutas", headers=fab.h, params={"fecha_desde": "2026-12-01", "fecha_hasta": "2026-11-01"})
    assert r.status_code == 400
