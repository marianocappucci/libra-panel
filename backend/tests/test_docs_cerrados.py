"""`/docs`, `/redoc` y `/openapi.json` no se publican en producción (ADR-053 de libracore).

Medido el 2026-10-15: `/openapi.json` daba 200 sin sesión en el panel real y publicaba el mapa de sus rutas. El
`docs_url=None` que ya tenía no alcanzaba: `openapi_url` seguía en su valor por omisión, y `/docs` y `/redoc` caían en el
fallback de la SPA, que contesta `index.html` con 200 a lo que no existe.

El criterio (sólo `ENV=development`, o `LIBRA_DOCS_API=1` a propósito) y su detalle tienen sus pruebas en libracore; acá se
fija que **este** panel lo usa, con la SPA montada como en producción.
"""
import pytest

from libra_panel import db
from libra_panel.app import create_app

from .conftest import hacer_cliente

RUTAS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<!doctype html><div id="root"></div>')
    return tmp_path


@pytest.fixture
def produccion(monkeypatch):
    """Lo que tiene una instancia real: ni `ENV=development` ni el interruptor del Swagger."""
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("LIBRA_DOCS_API", raising=False)


@pytest.mark.parametrize("ruta", RUTAS)
def test_en_produccion_con_la_spa_montada_dan_404_y_no_el_index(produccion, settings, dist, ruta):
    db.configure(settings.database_url)
    r = hacer_cliente(create_app(settings=settings, frontend_dist=str(dist))).get(ruta)
    assert r.status_code == 404, r.text[:200]
    assert "root" not in r.text and "openapi" not in r.text.lower()


def test_en_produccion_sin_spa_tambien(produccion, settings, tmp_path):
    db.configure(settings.database_url)
    c = hacer_cliente(create_app(settings=settings, frontend_dist=str(tmp_path / "no-existe")))
    assert {ruta: c.get(ruta).status_code for ruta in RUTAS} == dict.fromkeys(RUTAS, 404)


def test_en_desarrollo_se_sigue_viendo(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("LIBRA_DOCS_API", raising=False)
    db.configure(settings.database_url)
    c = hacer_cliente(create_app(settings=settings, frontend_dist=str(tmp_path / "no-existe")))
    esquema = c.get("/openapi.json")
    assert esquema.status_code == 200
    assert "/auth/login" in esquema.json()["paths"]
    assert c.get("/docs").status_code == 200


def test_el_resto_de_las_rutas_no_cambia(produccion, settings, dist):
    db.configure(settings.database_url)
    c = hacer_cliente(create_app(settings=settings, frontend_dist=str(dist)))
    assert c.get("/health").status_code == 200
    assert c.get("/sucursales").status_code == 200  # la SPA sigue atendiendo sus rutas
    assert c.get("/api/resumen").status_code == 401  # y la API sigue protegida
