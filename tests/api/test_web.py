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
    assert "ChessTrack AI" in r.text and '<script src="/static/app.js?v=' in r.text
    assert r.headers["cache-control"] == "no-cache"
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


def test_la_version_cambia_si_cambia_el_archivo_y_sin_cache_vieja(web, tmp_path, monkeypatch):
    import app.main as m

    v1 = m.portada_versionada()
    for nombre in ("index.html", "app.js", "style.css"):
        (tmp_path / nombre).write_bytes((m.WEB / nombre).read_bytes())
    (tmp_path / "app.js").write_text("// cambio", encoding="utf-8")
    monkeypatch.setattr(m, "WEB", tmp_path)
    v2 = m.portada_versionada()
    assert v1 != v2 and v1.split("style.css?v=")[1][:10] == v2.split("style.css?v=")[1][:10]
    assert web.get("/static/app.js").headers["cache-control"] == "no-cache"
