# -*- coding: utf-8 -*-
"""Parche 2: notas del chofer por parada y "no se pudo entregar" para poder seguir la ruta."""
API = "/api/v1"


def _codigo(client, h, eid):
    return client.get(f"{API}/entregas/{eid}", headers=h).json()["codigo_confirmacion"]


def _nota(client, ruta_id, parada_id, user, nota):
    return client.patch(f"{API}/rutas/{ruta_id}/paradas/{parada_id}/nota", headers=user["headers"], json={"nota": nota})


def _no_entregada(client, ruta_id, eid, user, **body):
    return client.patch(f"{API}/rutas/{ruta_id}/entregas/{eid}/no-entregada", headers=user["headers"], json=body)


def _confirmar(client, fab, ruta_id, eid, user):
    return client.patch(f"{API}/rutas/{ruta_id}/entregas/{eid}/confirmar", headers=user["headers"],
                        json={"codigo": _codigo(client, fab.h, eid)})


def _ruta(client, fab, rid):
    return client.get(f"{API}/rutas/{rid}", headers=fab.h).json()


# ── Notas ────────────────────────────────────────────────────────────────────

def test_nota_sin_confirmar_y_despues_de_confirmar(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    p1, p2, _ = ruta["paradas"]
    r = _nota(client, ruta["id"], p1["id"], chofer_a, "  Portón azul, tocar timbre dos veces  ")
    assert r.status_code == 200, r.text
    assert r.json()["paradas"][0]["nota_chofer"] == "Portón azul, tocar timbre dos veces"
    assert _confirmar(client, fab, ruta["id"], p1["entrega_id"], chofer_a).status_code == 200
    # ya confirmada, sigue pudiendo dejar/cambiar la nota
    assert _nota(client, ruta["id"], p1["id"], chofer_a, "Recibió el vecino").status_code == 200
    assert _ruta(client, fab, ruta["id"])["paradas"][0]["nota_chofer"] == "Recibió el vecino"


def test_el_admin_ve_la_nota_y_el_seguimiento_publico_no(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    _nota(client, ruta["id"], ruta["paradas"][0]["id"], chofer_a, "dato interno del chofer")
    assert _ruta(client, fab, ruta["id"])["paradas"][0]["nota_chofer"] == "dato interno del chofer"
    pub = client.get(f"{API}/seguimiento/{ruta['codigo_seguimiento']}")
    assert pub.status_code == 200
    assert "dato interno" not in pub.text


def test_borrar_nota(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    pid = ruta["paradas"][0]["id"]
    _nota(client, ruta["id"], pid, chofer_a, "algo")
    assert _nota(client, ruta["id"], pid, chofer_a, "   ").json()["paradas"][0]["nota_chofer"] is None
    assert _nota(client, ruta["id"], pid, chofer_a, None).status_code == 200


def test_nota_demasiado_larga_se_rechaza(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    assert _nota(client, ruta["id"], ruta["paradas"][0]["id"], chofer_a, "x" * 1001).status_code == 422


def test_otro_chofer_no_puede_dejar_nota(client, fab, chofer_a, chofer_b):
    ruta = fab.ruta_en_curso(chofer_a)
    assert _nota(client, ruta["id"], ruta["paradas"][0]["id"], chofer_b, "intruso").status_code == 403


def test_nota_solo_en_ruta_en_curso_y_parada_de_la_ruta(client, fab, chofer_a):
    sin_iniciar = fab.ruta(chofer=chofer_a)
    assert _nota(client, sin_iniciar["id"], sin_iniciar["paradas"][0]["id"], chofer_a, "x").status_code == 400
    en_curso = fab.ruta_en_curso(chofer_a)
    ajena = sin_iniciar["paradas"][0]["id"]
    assert _nota(client, en_curso["id"], ajena, chofer_a, "x").status_code == 404


# ── No se pudo entregar ──────────────────────────────────────────────────────

def test_no_entregada_libera_la_entrega_y_la_ruta_sigue(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    p1, p2, p3 = ruta["paradas"]
    r = _no_entregada(client, ruta["id"], p1["entrega_id"], chofer_a, motivo="nadie_recibio", nota="Nadie atendió, 2 intentos")
    assert r.status_code == 200, r.text
    parada = r.json()["paradas"][0]
    assert parada["omitida"] is True and parada["completada"] is False
    assert parada["motivo_omision"] == "nadie_recibio"
    assert parada["nota_chofer"] == "Nadie atendió, 2 intentos"
    assert r.json()["estado"] == "en_curso"
    entrega = client.get(f"{API}/entregas/{p1['entrega_id']}", headers=fab.h).json()
    assert entrega["estado"] == "pendiente"
    # puede seguir con las demás
    assert _confirmar(client, fab, ruta["id"], p2["entrega_id"], chofer_a).status_code == 200
    assert _confirmar(client, fab, ruta["id"], p3["entrega_id"], chofer_a).status_code == 200


def test_ruta_se_cierra_sola_cuando_todo_esta_resuelto(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a, cantidad=2)
    p1, p2 = ruta["paradas"]
    _confirmar(client, fab, ruta["id"], p1["entrega_id"], chofer_a)
    r = _no_entregada(client, ruta["id"], p2["entrega_id"], chofer_a)  # motivo por defecto: nadie_recibio
    assert r.status_code == 200
    assert r.json()["estado"] == "completada"
    assert r.json()["paradas"][1]["motivo_omision"] == "nadie_recibio"


def test_todas_no_entregadas_tambien_cierra_la_ruta(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a, cantidad=2)
    for p in ruta["paradas"]:
        r = _no_entregada(client, ruta["id"], p["entrega_id"], chofer_a, motivo="cliente_ausente")
    assert r.json()["estado"] == "completada"


def test_con_retorno_pasa_a_fase_regreso(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a, cantidad=1, retorno_tipo="otro", retorno_latitud=-34.7, retorno_longitud=-58.5)
    r = _no_entregada(client, ruta["id"], ruta["paradas"][0]["entrega_id"], chofer_a)
    assert r.json()["estado"] == "en_curso"
    assert r.json()["fase"] == "regreso"


def test_finalizar_con_omitidas_no_las_cuenta_como_pendientes(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a, cantidad=3, retorno_tipo="otro", retorno_latitud=-34.7, retorno_longitud=-58.5)
    p1, p2, p3 = ruta["paradas"]
    _confirmar(client, fab, ruta["id"], p1["entrega_id"], chofer_a)
    _no_entregada(client, ruta["id"], p2["entrega_id"], chofer_a)
    _no_entregada(client, ruta["id"], p3["entrega_id"], chofer_a)
    r = client.patch(f"{API}/rutas/{ruta['id']}/finalizar", headers=chofer_a["headers"])
    assert r.status_code == 200
    assert r.json()["estado"] == "completada"


def test_entrega_no_entregada_se_puede_replanificar(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a, cantidad=2)
    eid = ruta["paradas"][0]["entrega_id"]
    _no_entregada(client, ruta["id"], eid, chofer_a)
    nueva = client.post(f"{API}/rutas", headers=fab.h, json={
        "nombre": "Reintento", "entregas_ids": [eid], "origen_latitud": -34.61, "origen_longitud": -58.40})
    assert nueva.status_code == 201, nueva.text


def test_no_se_puede_confirmar_ni_repetir_una_no_entregada(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    eid = ruta["paradas"][0]["entrega_id"]
    _no_entregada(client, ruta["id"], eid, chofer_a)
    assert _confirmar(client, fab, ruta["id"], eid, chofer_a).status_code == 409
    assert _no_entregada(client, ruta["id"], eid, chofer_a).status_code == 400


def test_no_se_puede_marcar_no_entregada_una_ya_confirmada(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    eid = ruta["paradas"][0]["entrega_id"]
    _confirmar(client, fab, ruta["id"], eid, chofer_a)
    assert _no_entregada(client, ruta["id"], eid, chofer_a).status_code == 400
    assert client.get(f"{API}/entregas/{eid}", headers=fab.h).json()["estado"] == "completada"


def test_no_entregada_exige_ser_el_chofer_y_ruta_en_curso(client, fab, chofer_a, chofer_b):
    ruta = fab.ruta_en_curso(chofer_a)
    eid = ruta["paradas"][0]["entrega_id"]
    assert _no_entregada(client, ruta["id"], eid, chofer_b).status_code == 403
    sin_iniciar = fab.ruta(chofer=chofer_a)
    assert _no_entregada(client, sin_iniciar["id"], sin_iniciar["paradas"][0]["entrega_id"], chofer_a).status_code == 400


def test_motivo_invalido_se_rechaza(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    r = _no_entregada(client, ruta["id"], ruta["paradas"][0]["entrega_id"], chofer_a, motivo="porque si")
    assert r.status_code == 422


def test_seguimiento_publico_salta_las_omitidas(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a, cantidad=2)
    p1, p2 = ruta["paradas"]
    _no_entregada(client, ruta["id"], p1["entrega_id"], chofer_a)
    pub = client.get(f"{API}/seguimiento/{ruta['codigo_seguimiento']}").json()
    assert pub["progreso"] == 50
    assert pub["proxima_parada"]["orden"] == p2["orden"]
