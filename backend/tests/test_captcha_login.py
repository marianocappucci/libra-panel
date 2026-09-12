"""El captcha ALTCHA del login, cableado de verdad.

El resto de la suite corre con el captcha aprobado (fixture `_captcha_aprobado`
del conftest): el algoritmo lo prueba libraauth. Lo que es del PANEL, y lo que
fija este archivo, es el cableado:

1. Que `GET /auth/captcha` exista y devuelva un desafio con la forma que espera
   el widget de libra-ui (`parameters` + `signature`), sin cache.
2. 🔴 Que un login SIN captcha rebote con 400, aunque la contrasena sea buena.
   Si alguien sacara `captcha=True` de `libra_panel/app.py`, esto es lo que se
   pone rojo.
3. Que el forgot-password tambien lo exija.
4. Que con un desafio resuelto se entre.
"""
import os

import pytest
from libraauth.captcha import Captcha
from libraauth.session_auth import CAPTCHA_INVALIDO

from tests.conftest import _CAPTCHA_DE_ORIGINAL

CREDENCIALES_ADMIN = {"username": "admin", "password": os.environ["LIBRA_PANEL_ADMIN_PASSWORD"]}


@pytest.fixture(autouse=True)
def _captcha_real(monkeypatch, app):
    """La funcion real de libraauth, con un `Captcha` barato en el state.

    Barato para que resolver el desafio en el test tarde milisegundos y no el
    segundo que cuesta en el navegador. Se deja en el `app.state` de la app de
    ESTE test (el fixture `app` arma una nueva por test), asi que no le queda a
    nadie mas.
    """
    monkeypatch.setattr("libraauth.session_auth._captcha_de", _CAPTCHA_DE_ORIGINAL)
    app.state.captcha = Captcha("clave-de-prueba", costo=1, contador_min=1, contador_rango=5)


def test_el_desafio_tiene_la_forma_del_widget_y_no_se_cachea(client):
    r = client.get("/auth/captcha")
    assert r.status_code == 200, r.text
    desafio = r.json()
    assert isinstance(desafio.get("parameters"), dict)
    assert isinstance(desafio.get("signature"), str)
    assert "no-store" in r.headers.get("cache-control", "")


def test_login_sin_captcha_rebota_aunque_la_clave_sea_buena(client):
    r = client.post("/auth/login", json=CREDENCIALES_ADMIN)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == CAPTCHA_INVALIDO
    # Y no quedo sesion abierta.
    assert client.get("/auth/me").status_code == 401


def test_forgot_password_sin_captcha_rebota(client):
    r = client.post("/auth/forgot-password", json={"identificador": "admin"})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == CAPTCHA_INVALIDO


def test_login_con_el_desafio_resuelto_entra(client):
    from altcha import Challenge, Payload, solve_challenge

    desafio = Challenge.from_dict(client.get("/auth/captcha").json())
    solucion = Payload(desafio, solve_challenge(desafio)).to_base64()
    r = client.post("/auth/login", json={**CREDENCIALES_ADMIN, "captcha": solucion})
    assert r.status_code == 200, r.text
    # Y la sesion quedo abierta: no alcanza con el 200 del login.
    assert client.get("/auth/me").status_code == 200
