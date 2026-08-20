"""Arnes de la suite.

🔴 **Corre contra PostgreSQL de verdad, no contra SQLite.** Es la decision de
familia del 2026-08-12: una suite verde sobre SQLite no dice nada sobre el
motor real —no chequea FKs con el pragma apagado, tipa dinamicamente y acepta
cadenas donde la base pide enteros—, y este repo tiene justamente una FK
compuesta con `UNIQUE(usuario_id, sucursal_id)` cuyo trabajo es impedir que una
sucursal entre dos veces en el consolidado. Un motor que no la chequea la
volveria decorativa.

La URL sale de `LIBRA_PANEL_TEST_DATABASE_URL`. Si no esta, **la suite falla en
vez de caer a SQLite**: un fallback silencioso a otro motor es como se llega a
un verde que no prueba lo que dice probar.

La imagen es `postgres:16`, la misma que va a correr en produccion. No es un
detalle: el collation viene de la imagen y `alpine` ordena por bytes, asi que
una suite sobre alpine y una produccion sobre la normal ordenan distinto.
"""
import os
import time

# La zona horaria se fija ANTES de cualquier import que mire la hora, y no se
# hereda de la maquina: el panel calcula "el mes en curso" en hora de Argentina
# y una maquina en UTC devuelve otro rango durante las ultimas tres horas del
# dia. Estandar de la familia desde el 2026-08-12.
os.environ.setdefault("TZ", "America/Argentina/Buenos_Aires")
if hasattr(time, "tzset"):
    time.tzset()

# Secretos de la suite. `SECRET_KEY` no es solo la cookie: de el se deriva la
# clave con la que se cifran las credenciales de sucursal, asi que sin esto los
# tests del registro fallarian con `ClaveDeCifradoAusente`.
os.environ.setdefault("SECRET_KEY", "clave-de-test-del-panel-no-usar-en-produccion")
os.environ.setdefault("LIBRA_PANEL_ADMIN_PASSWORD", "admin-de-test")
os.environ.setdefault("LIBRA_PANEL_ADMIN_USERNAME", "admin")

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from libra_panel import db  # noqa: E402
from libra_panel.app import create_app  # noqa: E402
from libra_panel.settings import Settings  # noqa: E402

#: Tablas que la suite vacia entre tests. Se listan a mano y no se descubren
#: del metadata porque son de DOS metadatas distintas (libraauth y el panel) y
#: el orden importa: las hijas primero.
TABLAS = (
    "usuario_sucursales",
    "sucursales",
    "password_reset_tokens",
    "auth_log",
    "smtp_settings",
    "demo_codigos",
    "usuarios",
)


@pytest.fixture
def anyio_backend():
    """Los tests `async def` corren sobre asyncio y nada mas.

    Sin esta fixture, `pytest.mark.anyio` los correria sobre asyncio **y**
    trio, y trio no esta instalado: la suite quedaria con la mitad de los tests
    de concurrencia en error por un motivo que no tiene que ver con el panel.
    """
    return "asyncio"


def _url_de_test() -> str:
    url = (os.environ.get("LIBRA_PANEL_TEST_DATABASE_URL") or "").strip()
    if not url:
        pytest.exit(
            "Falta LIBRA_PANEL_TEST_DATABASE_URL. La suite corre contra "
            "PostgreSQL de verdad (postgres:16) y no cae a SQLite a proposito: "
            "ver el docstring de tests/conftest.py.",
            returncode=1,
        )
    return url


@pytest.fixture
def settings() -> Settings:
    return Settings(
        panel_name="Panel de test",
        database_url=_url_de_test(),
        # Corto: hay un test que mide que una sucursal colgada no arrastra a
        # las demas, y con el default de 6 s tardaria 6 s.
        timeout_sucursal=1.0,
        reset_url_base="https://panel.test/reset-password",
    )


@pytest.fixture
def crear_app(settings):
    """Fabrica de apps limpias.

    Se vacian las tablas **antes** y no despues: si un test se cae a la mitad,
    el siguiente sigue arrancando limpio en vez de heredar la basura del
    anterior y fallar por un motivo que no es el suyo.
    """

    def _crear(cliente_sucursal=None):
        db.configure(settings.database_url)
        with db.get_engine().begin() as conn:
            for tabla in TABLAS:
                conn.execute(text(f"DROP TABLE IF EXISTS {tabla} CASCADE"))
        return create_app(settings=settings, cliente_sucursal=cliente_sucursal)

    return _crear


@pytest.fixture
def app(crear_app):
    return crear_app()


def hacer_cliente(app):
    """Un `TestClient` sobre **https**, no sobre http.

    🔴 `SessionAuth.create_session_cookie` marca la cookie como `Secure`, que
    es lo correcto en produccion. Sobre `http://testserver` el cliente HTTP no
    la guarda ni la reenvia: el login devuelve 200 y **todo lo demas 401**, que
    se lee como un problema de permisos y no como lo que es. Cambiar la cookie
    para que la suite pase seria debilitar produccion para complacer al test.
    """
    from fastapi.testclient import TestClient

    return TestClient(app, base_url="https://testserver")


@pytest.fixture
def client(app):
    return hacer_cliente(app)


@pytest.fixture
def admin(client):
    """Un cliente ya logueado como el admin inicial."""
    resp = client.post(
        "/auth/login",
        json={"username": "admin", "password": os.environ["LIBRA_PANEL_ADMIN_PASSWORD"]},
    )
    assert resp.status_code == 200, resp.text
    return client
