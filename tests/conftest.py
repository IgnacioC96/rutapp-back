# -*- coding: utf-8 -*-
"""
Configuración común de los tests de RutApp.

Los tests usan una base PostgreSQL REAL (no mocks), porque varias reglas dependen del motor:
bloqueos de filas (SELECT ... FOR UPDATE), enums y UUID nativos.

    createdb rutapp_test
    set TEST_DATABASE_URL=postgresql://usuario:clave@localhost:5432/rutapp_test     (PowerShell: $env:TEST_DATABASE_URL="...")
    pip install -r requirements-dev.txt
    pytest

SEGURIDAD: el nombre de la base debe contener "test". Los tests borran y recrean las tablas, y se
niegan a correr contra cualquier otra base (para no pisar los datos de desarrollo).
"""
import os
import uuid

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if not TEST_DB:
    pytest.exit(
        "Falta la variable TEST_DATABASE_URL (ej: postgresql://user:pass@localhost:5432/rutapp_test). "
        "Ver tests/conftest.py",
        returncode=2,
    )
from sqlalchemy.engine import make_url  # noqa: E402

if "test" not in (make_url(TEST_DB).database or "").lower():
    pytest.exit("Por seguridad, la base de tests debe tener 'test' en su nombre.", returncode=2)

# Estas variables se leen al importar app.core.config, así que van ANTES de importar la app
os.environ["DATABASE_URL"] = TEST_DB
os.environ.setdefault("SECRET_KEY", "clave-solo-para-tests")
os.environ.setdefault("ORS_API_KEY", "sin-clave-los-tests-usan-un-mapa-falso")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import usuario, cliente, entrega, ruta, vehiculo, punto_salida  # noqa: E402,F401
from app.models.usuario import Usuario, RolUsuario  # noqa: E402
from app.core.security import crear_token, hashear_password  # noqa: E402
from app.api.routes import rutas as rutas_routes  # noqa: E402

Sesion = sessionmaker(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def esquema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def limpiar_tablas():
    yield
    with engine.begin() as conn:
        tablas = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def mapas_falsos(monkeypatch):
    """Sin red: el optimizador devuelve el orden recibido y la geocodificación una coordenada fija."""
    async def optimizar(origen, coords, retorno=None):
        return list(range(len(coords))), 12.5, 30, (2.0 if retorno else None), (5 if retorno else None)

    async def geocodificar(direccion):
        return (-58.6676, -34.6589)

    monkeypatch.setattr(rutas_routes, "optimizar_ruta", optimizar)
    monkeypatch.setattr(rutas_routes, "geocodificar_direccion", geocodificar)


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _crear_usuario(rol: RolUsuario, nombre: str):
    with Sesion() as db:
        u = Usuario(
            nombre=nombre,
            email=f"{nombre.lower().replace(' ', '')}.{uuid.uuid4().hex[:6]}@test.com",
            password_hash=hashear_password("Clave-Segura-123"),
            rol=rol,
            activo=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return {
            "id": str(u.id),
            "headers": {"Authorization": "Bearer " + crear_token({"sub": str(u.id), "rol": rol.value})},
        }


@pytest.fixture()
def admin():
    return _crear_usuario(RolUsuario.admin, "Admin")


@pytest.fixture()
def admin2():
    return _crear_usuario(RolUsuario.admin, "Admin Dos")


@pytest.fixture()
def chofer_a():
    return _crear_usuario(RolUsuario.chofer, "Chofer A")


@pytest.fixture()
def chofer_b():
    return _crear_usuario(RolUsuario.chofer, "Chofer B")


# ── Fábricas de datos ────────────────────────────────────────────────────────

class Fabrica:
    def __init__(self, client, headers):
        self.c, self.h = client, headers
        self.n = 0

    def entrega(self, **extra):
        """Crea un cliente (con una dirección principal) y una entrega pendiente. Devuelve el id."""
        self.n += 1
        r = self.c.post("/api/v1/clientes", headers=self.h, json={
            "nombre": f"Cliente {self.n} {uuid.uuid4().hex[:4]}",
            "telefono_whatsapp": f"11 5{self.n:03d}-{uuid.uuid4().int % 10000:04d}",
            "direcciones": [{"descripcion": f"Calle {self.n}", "es_principal": True,
                             "latitud": -34.60 - self.n / 100, "longitud": -58.50}],
        })
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        did = r.json()["direcciones"][0]["id"]
        r = self.c.post("/api/v1/entregas", headers=self.h,
                        json={"cliente_id": cid, "direccion_id": did, "descripcion": "Paquete", "bultos": 1, **extra})
        assert r.status_code == 201, r.text
        return r.json()["id"], cid, did

    def ruta(self, ids=None, cantidad=3, chofer=None, **extra):
        ids = ids or [self.entrega()[0] for _ in range(cantidad)]
        body = {"nombre": "Ruta de prueba", "entregas_ids": ids,
                "origen_latitud": -34.61, "origen_longitud": -58.40, **extra}
        r = self.c.post("/api/v1/rutas", headers=self.h, json=body)
        assert r.status_code == 201, r.text
        ruta = r.json()
        if chofer:
            r = self.c.patch(f"/api/v1/rutas/{ruta['id']}/asignar", headers=self.h, json={"chofer_id": chofer["id"]})
            assert r.status_code == 200, r.text
            ruta = r.json()
        return ruta

    def ruta_en_curso(self, chofer, **kw):
        ruta = self.ruta(chofer=chofer, **kw)
        r = self.c.patch(f"/api/v1/rutas/{ruta['id']}/iniciar", headers=chofer["headers"])
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture()
def fab(client, admin):
    return Fabrica(client, admin["headers"])
