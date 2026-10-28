# -*- coding: utf-8 -*-
"""Coordenadas estrictas: rangos válidos, par completo y nada de (0, 0) como "ubicación"."""
import pytest

API = "/api/v1"

INVALIDAS = [
    pytest.param({"latitud": 0, "longitud": 0}, id="cero-cero"),
    pytest.param({"latitud": 91, "longitud": -58.4}, id="latitud-mayor-90"),
    pytest.param({"latitud": -34.6, "longitud": 181}, id="longitud-mayor-180"),
    pytest.param({"latitud": -91, "longitud": -58.4}, id="latitud-menor-menos-90"),
    pytest.param({"latitud": -34.6}, id="falta-longitud"),
    pytest.param({"longitud": -58.4}, id="falta-latitud"),
]


@pytest.mark.parametrize("coords", INVALIDAS)
def test_direccion_de_cliente_rechaza_coordenadas_invalidas(client, admin, coords):
    r = client.post(f"{API}/clientes", headers=admin["headers"], json={
        "nombre": "Cliente", "telefono_whatsapp": "11 5555-0001",
        "direcciones": [{"descripcion": "Calle 1", "es_principal": True, **coords}],
    })
    assert r.status_code == 422, r.text


def test_direccion_de_cliente_acepta_coordenadas_validas_o_ausentes(client, admin):
    for coords in ({}, {"latitud": -34.6, "longitud": -58.4}):
        r = client.post(f"{API}/clientes", headers=admin["headers"], json={
            "nombre": "Cliente", "telefono_whatsapp": "11 5555-0001",
            "direcciones": [{"descripcion": "Calle 1", "es_principal": True, **coords}],
        })
        assert r.status_code == 201, r.text
        client.patch(f"{API}/clientes/{r.json()['id']}/baja", headers=admin["headers"])
        # el teléfono debe ser único entre clientes activos; se da de baja y se reintenta


@pytest.mark.parametrize("coords", [
    {"origen_latitud": 0, "origen_longitud": 0},
    {"origen_latitud": 95, "origen_longitud": -58.4},
    {"origen_latitud": -34.6},
])
def test_origen_de_ruta_rechaza_coordenadas_invalidas(client, fab, coords):
    eid = fab.entrega()[0]
    r = client.post(f"{API}/rutas", headers=fab.h, json={"nombre": "R", "entregas_ids": [eid], **coords})
    assert r.status_code == 422, r.text


def test_retorno_de_ruta_rechaza_cero_cero(client, fab):
    eid = fab.entrega()[0]
    r = client.post(f"{API}/rutas", headers=fab.h, json={
        "nombre": "R", "entregas_ids": [eid], "origen_latitud": -34.6, "origen_longitud": -58.4,
        "retorno_tipo": "otro", "retorno_latitud": 0, "retorno_longitud": 0})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("coords", INVALIDAS[:4])
def test_ubicacion_del_chofer_rechaza_coordenadas_invalidas(client, fab, chofer_a, coords):
    ruta = fab.ruta_en_curso(chofer_a)
    r = client.patch(f"{API}/rutas/{ruta['id']}/ubicacion", headers=chofer_a["headers"], json=coords)
    assert r.status_code == 422, r.text


def test_ubicacion_del_chofer_valida_se_guarda(client, fab, chofer_a):
    ruta = fab.ruta_en_curso(chofer_a)
    r = client.patch(f"{API}/rutas/{ruta['id']}/ubicacion", headers=chofer_a["headers"],
                     json={"latitud": -34.65, "longitud": -58.62})
    assert r.status_code == 200
    ruta = client.get(f"{API}/rutas/{ruta['id']}", headers=chofer_a["headers"]).json()
    assert ruta["chofer_latitud"] == pytest.approx(-34.65)


@pytest.mark.parametrize("coords", [{"latitud": 0, "longitud": 0}, {"latitud": 100, "longitud": 0}])
def test_parada_extra_y_punto_de_salida_rechazan_coordenadas_invalidas(client, fab, coords):
    ruta = fab.ruta()
    assert client.post(f"{API}/rutas/{ruta['id']}/paradas/extra", headers=fab.h,
                       json={"descripcion": "Nafta", **coords}).status_code == 422
    assert client.post(f"{API}/puntos-salida", headers=fab.h,
                       json={"nombre": "Depósito", "descripcion": "Calle 1", **coords}).status_code == 422
