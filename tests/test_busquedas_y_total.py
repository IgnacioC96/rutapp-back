# -*- coding: utf-8 -*-
"""Búsquedas por descripción/dirección y contador de entregas por cliente."""
API = "/api/v1"


def test_cliente_informa_su_total_de_entregas(client, fab, admin):
    _, cid, did = fab.entrega()
    client.post(f"{API}/entregas", headers=admin["headers"],
                json={"cliente_id": cid, "direccion_id": did, "descripcion": "Otro paquete", "bultos": 1})
    lista = client.get(f"{API}/clientes", headers=admin["headers"]).json()["clientes"]
    assert [c["total_entregas"] for c in lista if c["id"] == cid] == [2]
    assert client.get(f"{API}/clientes/{cid}", headers=admin["headers"]).json()["total_entregas"] == 2


def test_cliente_nuevo_tiene_cero_entregas(client, admin):
    r = client.post(f"{API}/clientes", headers=admin["headers"], json={
        "nombre": "Sin pedidos", "telefono_whatsapp": "11 5555-0000",
        "direcciones": [{"descripcion": "Calle 9", "es_principal": True}]})
    assert r.status_code == 201, r.text
    assert r.json()["total_entregas"] == 0


def test_buscar_entregas_por_descripcion(client, fab, admin):
    fab.entrega(descripcion="Medicamentos refrigerados")
    fab.entrega(descripcion="Pallet de bebidas")
    r = client.get(f"{API}/entregas", headers=admin["headers"], params={"search": "medicamentos"}).json()
    assert r["total"] == 1
    assert r["entregas"][0]["descripcion"] == "Medicamentos refrigerados"


def test_buscar_entregas_por_nombre_del_cliente_sigue_funcionando(client, fab, admin):
    _, cid, _ = fab.entrega()
    nombre = client.get(f"{API}/clientes/{cid}", headers=admin["headers"]).json()["nombre"]
    r = client.get(f"{API}/entregas", headers=admin["headers"], params={"search": nombre}).json()
    assert r["total"] == 1


def test_buscar_clientes_por_direccion(client, admin):
    for nombre, calle in (("Despensa Norte", "Rivadavia 25450, Ituzaingó"), ("Kiosco Sur", "Belgrano 100, Morón")):
        client.post(f"{API}/clientes", headers=admin["headers"], json={
            "nombre": nombre, "telefono_whatsapp": "11 5555-1111",
            "direcciones": [{"descripcion": calle, "es_principal": True}]})
    r = client.get(f"{API}/clientes", headers=admin["headers"], params={"search": "rivadavia"}).json()
    assert [c["nombre"] for c in r["clientes"]] == ["Despensa Norte"]
    assert r["total"] == 1
