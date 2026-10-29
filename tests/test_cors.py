# -*- coding: utf-8 -*-
"""CORS: los orígenes permitidos salen de CORS_ORIGINS."""
from app.core.config import Settings

API = "/api/v1"


def _settings(valor):
    return Settings(ORS_API_KEY="x", DATABASE_URL="postgresql://x/x_test", SECRET_KEY="x", CORS_ORIGINS=valor)


def test_lista_de_origenes_se_normaliza():
    s = _settings(" https://front.vercel.app/ , http://localhost:5173,, ")
    assert s.cors_origins_list == ["https://front.vercel.app", "http://localhost:5173"]


def test_por_defecto_solo_se_permite_desarrollo():
    s = Settings(ORS_API_KEY="x", DATABASE_URL="postgresql://x/x_test", SECRET_KEY="x", _env_file=None)
    assert s.cors_origins_list == ["http://localhost:3000", "http://localhost:5173"]


def test_origen_permitido_recibe_los_headers_cors(client):
    r = client.options(f"{API}/auth/login", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_origen_desconocido_no_recibe_headers_cors(client):
    r = client.options(f"{API}/auth/login", headers={
        "Origin": "https://sitio-malicioso.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
