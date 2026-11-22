"""La interfaz web se sirve desde la propia API (Etapa 6). No necesita BD."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def web():
    with TestClient(create_app()) as c:
        yield c


def test_portada_es_la_interfaz(web):
    r = web.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "ChessTrack AI" in r.text and '<script src="/static/app.js">' in r.text
    # Solo recursos propios: la CSP impide cargar scripts de terceros o inyectados
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    ("ruta", "tipo"), [("/static/app.js", "javascript"), ("/static/style.css", "text/css")]
)
def test_estaticos(web, ruta, tipo):
    r = web.get(ruta)
    assert r.status_code == 200 and tipo in r.headers["content-type"]


@pytest.mark.parametrize("ruta", ["/static/../main.py", "/static/%2e%2e/main.py", "/static/../../.env"])
def test_no_sirve_archivos_fuera_de_la_carpeta_web(web, ruta):
    assert web.get(ruta).status_code == 404


def test_la_portada_no_sale_en_la_documentacion(web):
    assert "/" not in web.get("/openapi.json").json()["paths"]
