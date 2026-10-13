"""El anti-replay del captcha vive en la base, no en el proceso (libraauth v0.50.0, ADR-023).

Con `uvicorn --workers N` (`WEB_CONCURRENCY`) la lista de desafios usados en memoria hace que un desafio resuelto
sirva una vez POR WORKER. El panel pasa `captcha_usados=UsadosEnBase(sessions)` al router de auth: este archivo fija
que el cableado esta y que anda de punta a punta con el `Captcha` real que arma el router (sin el doble barato de
`test_captcha_login.py`, que pisa `app.state.captcha`).
"""
import os

import pytest
from libraauth.captcha import UsadosEnBase
from libraauth.session_auth import CAPTCHA_INVALIDO
from sqlalchemy import text

from libra_panel import db
from tests.conftest import _CAPTCHA_DE_ORIGINAL

CREDENCIALES_ADMIN = {"username": "admin", "password": os.environ["LIBRA_PANEL_ADMIN_PASSWORD"]}


@pytest.fixture(autouse=True)
def _captcha_real(monkeypatch, app):
    monkeypatch.setattr("libraauth.session_auth._captcha_de", _CAPTCHA_DE_ORIGINAL)


def _resolver(client) -> str:
    from altcha import Challenge, Payload, solve_challenge

    desafio = Challenge.from_dict(client.get("/auth/captcha").json())
    return Payload(desafio, solve_challenge(desafio)).to_base64()


def test_el_captcha_del_router_anota_en_la_base(client):
    client.get("/auth/captcha")
    assert isinstance(client.app.state.captcha._usados, UsadosEnBase)


def test_un_desafio_resuelto_sirve_una_sola_vez_y_queda_anotado(client):
    solucion = _resolver(client)

    r = client.post("/auth/login", json={**CREDENCIALES_ADMIN, "captcha": solucion})
    assert r.status_code == 200, r.text
    with db.get_engine().connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM libraauth_captcha_usados")).scalar() == 1

    # El mismo desafio otra vez: rebota, aunque la clave sea buena.
    r = client.post("/auth/login", json={**CREDENCIALES_ADMIN, "captcha": solucion})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == CAPTCHA_INVALIDO


def test_otro_proceso_ve_el_mismo_desafio_como_usado(app, client):
    """Dos apps sobre la misma base = dos workers: el desafio que uso una no le sirve a la otra."""
    from libra_panel.app import create_app

    solucion = _resolver(client)
    assert client.post("/auth/login", json={**CREDENCIALES_ADMIN, "captcha": solucion}).status_code == 200

    # La otra "proceso": su propio `Captcha` (memoria vacia), la misma base y el mismo SECRET_KEY.
    otra = create_app(settings=app.state.settings)
    from tests.conftest import hacer_cliente

    otro_cliente = hacer_cliente(otra)
    r = otro_cliente.post("/auth/login", json={**CREDENCIALES_ADMIN, "captcha": solucion})
    assert r.status_code == 400, r.text
