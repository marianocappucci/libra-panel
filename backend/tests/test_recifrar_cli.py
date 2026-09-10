"""El comando que cierra una rotacion de `SECRET_KEY`.

Lo que fijan estos tests no es que imprima lindo, sino los **codigos de salida**:
son lo que mira quien corre el comando desde un `docker exec`, y son lo que
distingue "ya se puede sacar la variable" de "todavia no".
"""
import os

import pytest
from libraauth.crypto import CLAVES_ANTERIORES

from libra_panel.recifrar import main

CLAVE_VIEJA = "clave-de-test-del-panel-no-usar-en-produccion"


@pytest.fixture
def registro(app):
    """El registro de la app ya creada, que es la que corrio `create_all`."""
    return app.state.registro


@pytest.fixture(autouse=True)
def _url_en_el_entorno(monkeypatch):
    """El comando lee la URL del entorno, como en el contenedor."""
    monkeypatch.setenv(
        "LIBRA_PANEL_DATABASE_URL", os.environ["LIBRA_PANEL_TEST_DATABASE_URL"]
    )


def _crear(registro, slug="c1", credencial="secreta-1"):
    return registro.crear(
        slug=slug, nombre=slug.title(), url_base="http://c1:8000",
        cuit="30-71234567-9", razon_social="SA", credencial=credencial,
    )


def test_sin_url_de_base_sale_2_y_no_toca_nada(monkeypatch, capsys):
    """El 2 es "no pude ni intentar", que no es lo mismo que "no habia nada"."""
    monkeypatch.delenv("LIBRA_PANEL_DATABASE_URL", raising=False)
    assert main(["--ver"]) == 2


def test_ver_sin_pendientes_sale_0(app, registro, capsys):
    _crear(registro)
    assert main(["--ver"]) == 0
    assert "ninguna credencial" in capsys.readouterr().out


def test_ver_con_pendientes_sale_1_y_los_nombra(app, registro, monkeypatch, capsys):
    """Sale distinto de cero a proposito: quien lo corre en un script tiene que
    poder frenar antes de sacar la variable."""
    _crear(registro)
    monkeypatch.setenv("SECRET_KEY", "clave-nueva-del-panel-de-test")
    monkeypatch.setenv(CLAVES_ANTERIORES, CLAVE_VIEJA)
    assert main(["--ver"]) == 1
    assert "c1" in capsys.readouterr().out


def test_recifrar_sin_nada_que_hacer_sale_0(app, registro, capsys):
    _crear(registro)
    assert main([]) == 0
    assert "no habia nada que recifrar" in capsys.readouterr().out


def test_recifrar_cierra_la_rotacion(app, registro, monkeypatch, capsys):
    _crear(registro)
    monkeypatch.setenv("SECRET_KEY", "clave-nueva-del-panel-de-test")
    monkeypatch.setenv(CLAVES_ANTERIORES, CLAVE_VIEJA)

    assert main([]) == 0
    salida = capsys.readouterr().out
    assert "recifradas (1): c1" in salida
    assert "ya se puede sacar" in salida

    # Y lo confirma preguntando de nuevo, no dandolo por hecho.
    assert main(["--ver"]) == 0


def test_si_queda_alguna_ilegible_no_dice_que_cerro(app, registro, monkeypatch, capsys):
    """🔴 El comando no puede decir "ya se puede sacar la variable" si quedo
    algo que ningun recifrado va a arreglar. Vuelve a preguntar en vez de
    confiar en lo que acaba de hacer."""
    _crear(registro, "buena")
    monkeypatch.setenv("SECRET_KEY", "clave-huerfana-que-nadie-declara")
    monkeypatch.delenv(CLAVES_ANTERIORES, raising=False)
    _crear(registro, "rota", credencial="secreta-rota")

    monkeypatch.setenv("SECRET_KEY", "clave-nueva-del-panel-de-test")
    monkeypatch.setenv(CLAVES_ANTERIORES, CLAVE_VIEJA)
    assert main([]) == 0
    salida = capsys.readouterr().out
    assert "recifradas (1): buena" in salida
