# -*- coding: utf-8 -*-
"""El reordenamiento manual de paradas exige la secuencia completa 1..N, sin repetidos."""
API = "/api/v1"


def _orden(client, h, ruta, posiciones):
    return client.patch(f"{API}/rutas/{ruta['id']}/paradas", headers=h, json={
        "paradas": [{"parada_id": p["id"], "orden": o} for p, o in zip(ruta["paradas"], posiciones)]})


def test_orden_valido_se_aplica(client, fab):
    ruta = fab.ruta(cantidad=3)
    r = _orden(client, fab.h, ruta, [3, 1, 2])
    assert r.status_code == 200, r.text
    assert [p["id"] for p in r.json()["paradas"]] == [ruta["paradas"][1]["id"], ruta["paradas"][2]["id"], ruta["paradas"][0]["id"]]


def test_posiciones_repetidas_se_rechazan(client, fab):
    ruta = fab.ruta(cantidad=3)
    assert _orden(client, fab.h, ruta, [1, 1, 2]).status_code == 400


def test_posiciones_salteadas_o_fuera_de_rango_se_rechazan(client, fab):
    ruta = fab.ruta(cantidad=3)
    assert _orden(client, fab.h, ruta, [1, 2, 5]).status_code == 400
    assert _orden(client, fab.h, ruta, [0, 1, 2]).status_code in (400, 422)
    assert _orden(client, fab.h, ruta, [2, 3, 4]).status_code == 400


def test_secuencia_incompleta_se_rechaza(client, fab):
    ruta = fab.ruta(cantidad=3)
    r = client.patch(f"{API}/rutas/{ruta['id']}/paradas", headers=fab.h, json={
        "paradas": [{"parada_id": ruta["paradas"][0]["id"], "orden": 1}, {"parada_id": ruta["paradas"][1]["id"], "orden": 2}]})
    assert r.status_code == 400
    assert "incompleto" in r.text


def test_parada_repetida_se_rechaza(client, fab):
    ruta = fab.ruta(cantidad=2)
    p = ruta["paradas"][0]["id"]
    r = client.patch(f"{API}/rutas/{ruta['id']}/paradas", headers=fab.h, json={
        "paradas": [{"parada_id": p, "orden": 1}, {"parada_id": p, "orden": 2}]})
    assert r.status_code == 400


def test_parada_de_otra_ruta_se_rechaza(client, fab):
    r1, r2 = fab.ruta(cantidad=2), fab.ruta(cantidad=2)
    r = client.patch(f"{API}/rutas/{r1['id']}/paradas", headers=fab.h, json={
        "paradas": [{"parada_id": r1["paradas"][0]["id"], "orden": 1}, {"parada_id": r2["paradas"][0]["id"], "orden": 2}]})
    assert r.status_code == 400


def test_no_se_reordena_una_ruta_en_curso(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    assert _orden(client, fab.h, ruta, [2, 1, 3]).status_code == 400


def test_orden_con_parada_extra_incluida(client, fab):
    ruta = fab.ruta(cantidad=2)
    r = client.post(f"{API}/rutas/{ruta['id']}/paradas/extra", headers=fab.h, json={"descripcion": "Nafta"})
    ruta = r.json()
    assert len(ruta["paradas"]) == 3
    assert _orden(client, fab.h, ruta, [3, 2, 1]).status_code == 200
