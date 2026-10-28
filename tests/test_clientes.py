# -*- coding: utf-8 -*-
"""Las reglas de negocio de CREAR un cliente también se cumplen al EDITARLO."""
API = "/api/v1"


def _cliente(client, h, direcciones=None):
    r = client.post(f"{API}/clientes", headers=h, json={
        "nombre": "Cliente Reglas", "telefono_whatsapp": "11 5555-1234",
        "direcciones": direcciones or [{"descripcion": "Calle 1", "es_principal": True}],
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_editar_sin_direccion_principal_se_rechaza(client, admin):
    c = _cliente(client, admin["headers"])
    r = client.put(f"{API}/clientes/{c['id']}", headers=admin["headers"],
                   json={"direcciones": [{"descripcion": "Calle 1", "es_principal": False}]})
    assert r.status_code == 422
    assert "principal" in r.text


def test_editar_con_dos_principales_se_rechaza(client, admin):
    c = _cliente(client, admin["headers"])
    r = client.put(f"{API}/clientes/{c['id']}", headers=admin["headers"], json={"direcciones": [
        {"descripcion": "A", "es_principal": True}, {"descripcion": "B", "es_principal": True}]})
    assert r.status_code == 422


def test_editar_con_lista_vacia_o_mas_de_tres_se_rechaza(client, admin):
    c = _cliente(client, admin["headers"])
    assert client.put(f"{API}/clientes/{c['id']}", headers=admin["headers"], json={"direcciones": []}).status_code == 422
    cuatro = [{"descripcion": f"D{i}", "es_principal": i == 0} for i in range(4)]
    assert client.put(f"{API}/clientes/{c['id']}", headers=admin["headers"], json={"direcciones": cuatro}).status_code == 422


def test_editar_sin_mandar_direcciones_no_las_toca(client, admin):
    c = _cliente(client, admin["headers"])
    r = client.put(f"{API}/clientes/{c['id']}", headers=admin["headers"], json={"nombre": "Nuevo nombre"})
    assert r.status_code == 200
    assert r.json()["nombre"] == "Nuevo nombre"
    assert len(r.json()["direcciones"]) == 1


def test_cambiar_la_principal_deja_una_sola(client, admin):
    c = _cliente(client, admin["headers"], [
        {"descripcion": "A", "es_principal": True}, {"descripcion": "B", "es_principal": False}])
    a, b = c["direcciones"]
    r = client.put(f"{API}/clientes/{c['id']}", headers=admin["headers"], json={"direcciones": [
        {"id": a["id"], "descripcion": "A", "es_principal": False},
        {"id": b["id"], "descripcion": "B", "es_principal": True}]})
    assert r.status_code == 200, r.text
    assert [d["es_principal"] for d in r.json()["direcciones"]].count(True) == 1


def test_direccion_con_entregas_no_queda_como_segunda_principal(client, fab, admin):
    """Una dirección con entregas no se puede borrar: si no viene en el request, deja de ser principal."""
    eid, cid, did = fab.entrega()
    r = client.put(f"{API}/clientes/{cid}", headers=admin["headers"], json={"direcciones": [
        {"descripcion": "Dirección nueva", "es_principal": True}]})
    assert r.status_code == 200, r.text
    principales = [d for d in r.json()["direcciones"] if d["es_principal"]]
    assert len(principales) == 1 and principales[0]["descripcion"] == "Dirección nueva"
    assert any(d["id"] == did for d in r.json()["direcciones"])  # la vieja se conserva (tiene entregas)


def test_direccion_vacia_se_rechaza(client, admin):
    r = client.post(f"{API}/clientes", headers=admin["headers"], json={
        "nombre": "X", "telefono_whatsapp": "11 5555-9999",
        "direcciones": [{"descripcion": "   ", "es_principal": True}]})
    assert r.status_code == 422
