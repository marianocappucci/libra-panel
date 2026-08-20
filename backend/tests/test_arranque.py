"""Lo que tiene que fallar al arrancar, y lo que sirve la SPA.

Un panel que levanta y recien revienta cuando el dueño abre la pantalla es un
despliegue que parece exitoso. Estos tests son los que hacen que no exista esa
version.
"""
import datetime

import pytest

from libra_panel import db
from libra_panel.app import create_app
from libra_panel.fechas import AR_TZ, a_dd_mm_aaaa, hoy_ar, rango_por_defecto
from libra_panel.settings import ConfiguracionInvalida, cargar_settings

BASE = "postgresql://panel:panel@127.0.0.1:55432/panel"


# ── Settings ────────────────────────────────────────────────────────────────


def test_sin_url_de_base_no_arranca():
    with pytest.raises(ConfiguracionInvalida) as exc:
        cargar_settings({})
    assert "LIBRA_PANEL_DATABASE_URL" in str(exc.value)


def test_el_timeout_por_defecto_es_corto():
    from libra_panel.settings import TIMEOUT_POR_DEFECTO

    assert cargar_settings({"LIBRA_PANEL_DATABASE_URL": BASE}).timeout_sucursal == TIMEOUT_POR_DEFECTO
    assert TIMEOUT_POR_DEFECTO <= 10


def test_un_timeout_que_no_es_numero_no_arranca():
    with pytest.raises(ConfiguracionInvalida):
        cargar_settings({"LIBRA_PANEL_DATABASE_URL": BASE, "TIMEOUT_SUCURSAL": "un-rato"})


def test_un_timeout_de_cero_no_arranca():
    """Sin timeout, una sola sucursal colgada cuelga la pantalla entera."""
    with pytest.raises(ConfiguracionInvalida) as exc:
        cargar_settings({"LIBRA_PANEL_DATABASE_URL": BASE, "TIMEOUT_SUCURSAL": "0"})
    assert "mayor que cero" in str(exc.value)


def test_el_nombre_del_panel_sale_del_entorno():
    """El panel es transversal: el branding no puede estar en el codigo."""
    s = cargar_settings({"LIBRA_PANEL_DATABASE_URL": BASE, "PANEL_NAME": "Complejos Pádel"})
    assert s.panel_name == "Complejos Pádel"


# ── La guarda de PostgreSQL ─────────────────────────────────────────────────


@pytest.mark.parametrize("url", [
    "sqlite:///panel.db",
    "sqlite:////tmp/panel.db",
    "mysql://x/y",
])
def test_no_arranca_contra_otro_motor(url):
    """🔴 Una suite verde sobre SQLite no dice nada sobre el motor real.

    Es la decision de familia del 2026-08-12, y este repo tiene una razon
    propia: la `UNIQUE(usuario_id, sucursal_id)` que impide que una sucursal
    entre dos veces en el consolidado no la chequea SQLite con el pragma
    apagado.
    """
    with pytest.raises(ValueError) as exc:
        db.configure(url)
    assert "PostgreSQL" in str(exc.value)


def test_la_url_pelada_se_normaliza_al_driver_de_la_familia():
    """`postgresql://` a secas resuelve a psycopg2, que no esta instalado — y
    falla al IMPORTARSE, asi que el contenedor ni llega a levantar."""
    db.configure(BASE)
    assert db.get_engine().url.drivername == "postgresql+psycopg"


def test_la_url_con_driver_explicito_tambien_sirve():
    db.configure(BASE.replace("postgresql://", "postgresql+psycopg://", 1))
    assert db.get_engine().url.drivername == "postgresql+psycopg"


# ── Fecha y hora ────────────────────────────────────────────────────────────


def test_la_zona_es_utc_menos_3_sin_horario_de_verano():
    enero = datetime.datetime(2026, 1, 15, tzinfo=AR_TZ)
    julio = datetime.datetime(2026, 7, 15, tzinfo=AR_TZ)
    assert enero.utcoffset() == julio.utcoffset() == datetime.timedelta(hours=-3)


def test_hoy_es_el_dia_de_argentina_y_no_el_de_la_maquina():
    """🔴 Entre las 21:00 y la medianoche de Argentina, una maquina en UTC ya
    esta en el dia siguiente: el mes en curso arrancaria el 1 del mes que viene
    y el panel mostraria todo en cero."""
    assert hoy_ar() == datetime.datetime.now(AR_TZ).date()


def test_el_rango_por_defecto_es_el_mes_en_curso():
    desde, hasta = rango_por_defecto()
    assert desde == hoy_ar().replace(day=1).isoformat()
    assert hasta == hoy_ar().isoformat()
    # ISO y no dd-mm-aaaa: es lo que se le reenvia a cada sucursal.
    assert desde[4] == "-"


@pytest.mark.parametrize("entrada,esperado", [
    ("2026-08-20", "20-08-2026"),
    (datetime.date(2026, 1, 5), "05-01-2026"),
    ("no es una fecha", "no es una fecha"),
])
def test_el_formato_visible_es_dd_mm_aaaa(entrada, esperado):
    assert a_dd_mm_aaaa(entrada) == esperado


# ── La SPA ──────────────────────────────────────────────────────────────────


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Panel</title>")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    return tmp_path


def test_una_ruta_de_la_spa_devuelve_el_index(settings, dist):
    from .conftest import hacer_cliente

    db.configure(settings.database_url)
    cliente = hacer_cliente(create_app(settings=settings, frontend_dist=str(dist)))
    resp = cliente.get("/sucursales")
    assert resp.status_code == 200
    assert "<!doctype html>" in resp.text


def test_el_index_no_se_cachea(settings, dist):
    """🔴 Sin esto el deploy queda correcto e invisible.

    El navegador se queda con el HTML viejo, que referencia el bundle viejo por
    su hash — y ese bundle sigue existiendo y sigue devolviendo 200. La version
    nueva esta servida y nadie la ve.
    """
    from .conftest import hacer_cliente

    db.configure(settings.database_url)
    cliente = hacer_cliente(create_app(settings=settings, frontend_dist=str(dist)))
    assert cliente.get("/").headers["cache-control"] == "no-cache"
    assert cliente.get("/sucursales").headers["cache-control"] == "no-cache"


def test_el_bundle_con_hash_si_se_puede_cachear(settings, dist):
    """Control del anterior: `no-cache` en todo tiraria a la basura el hash del
    nombre, que es justamente lo que permite cachear fuerte."""
    from .conftest import hacer_cliente

    db.configure(settings.database_url)
    cliente = hacer_cliente(create_app(settings=settings, frontend_dist=str(dist)))
    resp = cliente.get("/assets/app-abc123.js")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") != "no-cache"


def test_la_api_gana_sobre_el_catch_all_de_la_spa(settings, dist):
    """Si el catch-all se comiera `/api/...`, el 401 seria un 200 con HTML."""
    from .conftest import hacer_cliente

    db.configure(settings.database_url)
    cliente = hacer_cliente(create_app(settings=settings, frontend_dist=str(dist)))
    resp = cliente.get("/api/resumen")
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/json")


def test_sin_frontend_construido_la_app_levanta_igual(settings, tmp_path):
    """En desarrollo el frontend lo sirve Vite en otro puerto."""
    db.configure(settings.database_url)
    app = create_app(settings=settings, frontend_dist=str(tmp_path / "no-existe"))
    from .conftest import hacer_cliente

    assert hacer_cliente(app).get("/health").status_code == 200
