"""El registro de errores de la familia, cableado de verdad (ADR-045 de libracore).

Lo que prueba el motor (la limpieza de datos, la firma, la rotacion) lo prueba libracore. Lo que es del PANEL, y lo
que fija este archivo, es el cableado: que `create_app` instale `instalar_registro_de_errores`, de modo que

1. una ruta que revienta conteste `500` con un `ref` y deje UNA linea en el `errores.jsonl` (el que lee el vigia),
   con el producto y la instancia que corresponden;
2. los 4xx de siempre (login mal, sin sesion) no ensucien el registro;
3. exista `POST /api/errores-cliente`, a donde manda `instalarReporteDeErrores` de libra-ui, sin pedir sesion.

Si alguien sacara la linea de `app.py`, los tres se ponen rojos.
"""
import json
import os

import pytest

from tests.conftest import hacer_cliente


@pytest.fixture
def carpeta_de_errores(tmp_path, monkeypatch):
    """`LIBRA_ERRORES_DIR` a un temporal: la suite nunca escribe en el cwd."""
    carpeta = tmp_path / "errores"
    monkeypatch.setenv("LIBRA_ERRORES_DIR", str(carpeta))
    monkeypatch.setenv("LIBRA_ENTORNO", "cliente")
    monkeypatch.setenv("LIBRA_INSTANCIA", "libra-panel")
    return carpeta


def _lineas(carpeta) -> list[dict]:
    archivo = carpeta / "errores.jsonl"
    if not archivo.exists():
        return []
    return [json.loads(linea) for linea in archivo.read_text(encoding="utf-8").splitlines() if linea.strip()]


def test_un_500_responde_con_ref_y_deja_una_linea(app, carpeta_de_errores):
    @app.get("/api/_explota/{cosa}")
    def explota(cosa: str):
        raise ValueError(f"se rompio {cosa}")

    # `raise_server_exceptions=False`: el TestClient, si no, relanza lo que uvicorn tambien ve.
    client = hacer_cliente(app)
    client._transport.raise_server_exceptions = False
    r = client.get("/api/_explota/42")

    assert r.status_code == 500, r.text
    cuerpo = r.json()
    assert cuerpo["detail"] == "Error interno"
    assert len(cuerpo["ref"]) == 8
    lineas = _lineas(carpeta_de_errores)
    assert len(lineas) == 1, lineas
    linea = lineas[0]
    assert linea["ref"] == cuerpo["ref"]
    assert linea["producto"] == "libra-panel"
    assert linea["instancia"] == "libra-panel"
    assert linea["entorno"] == "cliente"
    assert linea["origen"] == "servidor"
    assert linea["status"] == 500
    assert linea["tipo"] == "ValueError"
    # La plantilla de la ruta, nunca la URL con el id.
    assert linea["ruta"] == "/api/_explota/{cosa}"


def test_los_4xx_no_se_registran(client, carpeta_de_errores):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/api/sucursales").status_code in (401, 403)
    assert client.post("/auth/login", json={"username": "admin"}).status_code == 422
    assert _lineas(carpeta_de_errores) == []


def test_el_navegador_puede_reportar_sin_sesion(client, carpeta_de_errores):
    """`POST /api/errores-cliente` es publico a proposito (un error del login tambien importa)."""
    r = client.post(
        "/api/errores-cliente",
        json={"tipo": "render", "mensaje": "x is undefined", "stack": "at Panel (bundle.js:1:2)",
              "pagina": "/sucursales", "release": "abc123"},
        headers={"Origin": "https://testserver"},
    )
    assert r.status_code == 204, r.text
    lineas = _lineas(carpeta_de_errores)
    assert len(lineas) == 1
    assert lineas[0]["origen"] == "cliente"
    assert lineas[0]["producto"] == "libra-panel"
    assert lineas[0]["ruta"] == "/sucursales"


def test_el_archivo_cae_donde_dice_la_variable(app, carpeta_de_errores):
    """El volumen del compose se monta en `LIBRA_ERRORES_DIR`: el vigia lee de ahi."""

    @app.get("/api/_explota")
    def explota():
        raise RuntimeError("boom")

    client = hacer_cliente(app)
    client._transport.raise_server_exceptions = False
    client.get("/api/_explota")
    assert os.path.isfile(carpeta_de_errores / "errores.jsonl")
