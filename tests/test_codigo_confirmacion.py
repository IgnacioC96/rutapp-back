# -*- coding: utf-8 -*-
"""El código de confirmación es un secreto aleatorio: no se deduce del UUID ni se puede adivinar."""
import re
API = "/api/v1"


def _codigo(client, h, eid):
    return client.get(f"{API}/entregas/{eid}", headers=h).json()["codigo_confirmacion"]


def test_codigo_no_se_deriva_del_uuid(client, fab):
    for _ in range(5):
        eid = fab.entrega()[0]
        codigo = _codigo(client, fab.h, eid)
        sin_guiones = eid.replace("-", "").upper()
        assert codigo.upper() not in sin_guiones
        assert codigo.upper() != eid.split("-")[0].upper()
        assert codigo.upper() != sin_guiones[-len(codigo):]


def test_codigos_son_distintos_y_con_formato_esperado(client, fab):
    codigos = {_codigo(client, fab.h, fab.entrega()[0]) for _ in range(12)}
    assert len(codigos) == 12
    assert all(re.fullmatch(r"[0-9A-Fa-f]{8}", c) for c in codigos)


def test_codigo_incorrecto_no_confirma(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    eid = ruta["paradas"][0]["entrega_id"]
    r = client.patch(f"{API}/rutas/{ruta['id']}/entregas/{eid}/confirmar", headers=chofer_a["headers"], json={"codigo": "00000000"})
    assert r.status_code == 400
    # Intentar con el UUID de la entrega (lo único que el chofer podría ver) tampoco sirve
    for intento in (eid, eid.replace("-", "")[:8], eid.split("-")[0]):
        r = client.patch(f"{API}/rutas/{ruta['id']}/entregas/{eid}/confirmar", headers=chofer_a["headers"], json={"codigo": intento})
        assert r.status_code == 400
    assert client.get(f"{API}/entregas/{eid}", headers=fab.h).json()["estado"] == "en_curso"


def test_codigo_correcto_acepta_minusculas_y_prefijo_qr(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    for parada, variante in zip(ruta["paradas"], (lambda c: c.lower(), lambda c: "QR-" + c, lambda c: c)):
        eid = parada["entrega_id"]
        codigo = _codigo(client, fab.h, eid)
        r = client.patch(f"{API}/rutas/{ruta['id']}/entregas/{eid}/confirmar", headers=chofer_a["headers"], json={"codigo": variante(codigo)})
        assert r.status_code == 200, r.text


def test_no_se_confirma_en_una_ruta_que_no_esta_en_curso(client, fab, chofer_a):
    ruta = fab.ruta(chofer=chofer_a)  # asignada, sin iniciar
    eid = ruta["paradas"][0]["entrega_id"]
    codigo = _codigo(client, fab.h, eid)
    r = client.patch(f"{API}/rutas/{ruta['id']}/entregas/{eid}/confirmar", headers=chofer_a["headers"], json={"codigo": codigo})
    assert r.status_code == 400
