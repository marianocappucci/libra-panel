"""`GET /api/salud`: cuáles sucursales contestan, y que no mienta ni se cuelgue.

Dos capas, como en el resto de la suite:

- **El cliente** (`ClienteSucursal.salud`) contra apps FastAPI de verdad por
  `ASGITransport`: lo que se prueba es el contrato de cable, sobre todo que un
  200 con el `index.html` de la SPA NO cuente como «viva».
- **El router** con un cliente doble, para lo que es del router: paralelo,
  alcance por usuario, una caída que no arrastra a las demás.
"""
import asyncio
import time

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from libra_panel.cliente_sucursal import HEADER_CREDENCIAL, ClienteSucursal, SucursalSinRespuesta

from .conftest import hacer_cliente
from .sucursal_falsa import HTML_DE_LA_SPA

# ── El cliente, contra apps de verdad ───────────────────────────────────────


def cliente_contra(app, *, timeout_salud: float = 2.0) -> ClienteSucursal:
    return ClienteSucursal(
        timeout=5.0, timeout_salud=timeout_salud, transport=httpx.ASGITransport(app=app)
    )


def instancia(cuerpo, *, status: int = 200, demora: float = 0.0, con_spa: bool = True) -> FastAPI:
    """Una instancia que contesta `cuerpo` en `/health`, y la SPA en el resto."""
    app = FastAPI()
    app.state.headers_recibidos = []

    @app.get("/health")
    async def health(request: Request):
        app.state.headers_recibidos.append(dict(request.headers))
        if demora:
            await asyncio.sleep(demora)
        if status >= 400:
            raise HTTPException(status, "se rompio")
        if isinstance(cuerpo, str):
            return HTMLResponse(cuerpo)
        return cuerpo

    if con_spa:
        @app.get("/{ruta:path}", include_in_schema=False)
        def spa(ruta: str):
            return HTMLResponse(HTML_DE_LA_SPA)

    return app


@pytest.mark.anyio
@pytest.mark.parametrize("cuerpo", [
    {"status": "ok"},                                     # contalibra, restolibra
    {"ok": True, "product": "gestiolibra"},               # gestiolibra, medlibra, ventalibra
    {"estado": "ok", "ts": "2026-10-15T10:00:00"},        # libraclub, libracargo
    {},                                                   # sin ninguna clave en particular
])
async def test_las_formas_de_health_de_la_familia_dan_viva(cuerpo):
    """Pedir una clave concreta pondria en rojo a productos sanos."""
    datos = await cliente_contra(instancia(cuerpo)).salud(url_base="http://sucursal")
    assert datos == {"version": None}


@pytest.mark.anyio
async def test_la_version_sale_del_cuerpo_si_la_instancia_la_manda():
    datos = await cliente_contra(instancia({"ok": True, "version": "v2026.10.12-103000"})).salud(
        url_base="http://sucursal"
    )
    assert datos["version"] == "v2026.10.12-103000"


@pytest.mark.anyio
@pytest.mark.parametrize("version", [None, "", 3, ["v1"], {"a": 1}])
async def test_una_version_que_no_es_texto_no_se_inventa(version):
    datos = await cliente_contra(instancia({"ok": True, "version": version})).salud(
        url_base="http://sucursal"
    )
    assert datos["version"] is None


@pytest.mark.anyio
async def test_un_200_con_el_html_de_la_spa_NO_es_una_instancia_viva():
    """🔴 El caso que motiva el chequeo del cuerpo: una `url_base` mal cargada
    contesta 200 con `index.html`. Mirando sólo el código, daría verde."""
    with pytest.raises(SucursalSinRespuesta) as exc:
        await cliente_contra(instancia(HTML_DE_LA_SPA)).salud(url_base="http://sucursal")
    assert "no es JSON" in exc.value.detalle
    assert "SPA" in exc.value.detalle


@pytest.mark.anyio
async def test_una_ruta_inexistente_en_una_instancia_con_catch_all_tambien_cae():
    """Mismo caso pero sin tocar `/health`: el catch-all contesta por una ruta que
    el chequeo no controla. Se prueba con una instancia que NO define /health."""
    app = FastAPI()

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        return HTMLResponse(HTML_DE_LA_SPA)

    with pytest.raises(SucursalSinRespuesta):
        await cliente_contra(app).salud(url_base="http://sucursal")


@pytest.mark.anyio
@pytest.mark.parametrize("cuerpo, tipo", [([1, 2], "list"), ("texto", "str"), (3, "int"), (None, "NoneType")])
async def test_un_json_que_no_es_objeto_no_es_un_health(cuerpo, tipo):
    app = FastAPI()

    @app.get("/health")
    def health():
        return cuerpo

    with pytest.raises(SucursalSinRespuesta) as exc:
        await cliente_contra(app).salud(url_base="http://sucursal")
    assert tipo in exc.value.detalle


@pytest.mark.anyio
async def test_un_5xx_sale_con_su_codigo_y_su_detalle():
    with pytest.raises(SucursalSinRespuesta) as exc:
        await cliente_contra(instancia({}, status=503)).salud(url_base="http://sucursal")
    assert exc.value.detalle == "HTTP 503: se rompio"


@pytest.mark.anyio
async def test_una_conexion_rechazada_es_una_sucursal_caida_y_no_un_error_del_panel():
    def rechaza(request):
        raise httpx.ConnectError("conexion rechazada", request=request)

    cliente = ClienteSucursal(timeout=5.0, transport=httpx.MockTransport(rechaza))
    with pytest.raises(SucursalSinRespuesta) as exc:
        await cliente.salud(url_base="http://sucursal")
    assert "ConnectError" in exc.value.detalle


@pytest.mark.anyio
async def test_una_instancia_colgada_vence_por_el_tope_y_lo_dice():
    """El tope es de pared: la instancia contesta, pero tarde."""
    inicio = time.monotonic()
    with pytest.raises(SucursalSinRespuesta) as exc:
        await cliente_contra(instancia({"ok": True}, demora=5.0), timeout_salud=0.2).salud(
            url_base="http://sucursal"
        )
    assert time.monotonic() - inicio < 2.0
    assert "0.2 s" in exc.value.detalle


@pytest.mark.anyio
async def test_el_health_no_lleva_la_credencial_de_panel():
    """El `/health` es público: la credencial no tiene por qué viajar ahí."""
    app = instancia({"ok": True})
    await cliente_contra(app).salud(url_base="http://sucursal")
    (headers,) = app.state.headers_recibidos
    assert HEADER_CREDENCIAL.lower() not in headers


@pytest.mark.anyio
async def test_la_barra_final_de_url_base_no_duplica_la_barra():
    visto = []

    def maneja(request):
        visto.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    cliente = ClienteSucursal(timeout=5.0, transport=httpx.MockTransport(maneja))
    await cliente.salud(url_base="http://sucursal:8000/")
    assert visto == ["http://sucursal:8000/health"]


# ── El router ───────────────────────────────────────────────────────────────


class ClienteDeSalud:
    """Contesta según la `url_base`; puede demorar, caerse o explotar por sucursal."""

    def __init__(self, respuestas: dict, *, demora: float = 0.0):
        self.respuestas = respuestas
        self.demora = demora
        self.llamadas: list[str] = []

    async def salud(self, *, url_base):
        self.llamadas.append(url_base)
        if self.demora:
            await asyncio.sleep(self.demora)
        valor = self.respuestas.get(url_base, {"version": None})
        if isinstance(valor, Exception):
            raise valor
        return valor

    async def resumen(self, **_):  # pragma: no cover - /api/salud no lo usa
        raise AssertionError("/api/salud no tiene que pedir el resumen")


def alta(cliente, slug, *, credencial="cred-secreta"):
    resp = cliente.post("/api/sucursales", json={
        "slug": slug, "nombre": slug.title(), "url_base": f"http://{slug}:8000",
        "cuit": "30-71234567-9", "razon_social": "Padel SA", "credencial": credencial,
    })
    assert resp.status_code == 201, resp.text


def asignar_al_admin(cliente, slugs):
    uid = int(cliente.get("/auth/me").json()["id"])
    for slug in slugs:
        assert cliente.put(f"/api/sucursales/{slug}/usuarios", json={"usuario_ids": [uid]}).status_code == 200


@pytest.fixture
def con_cinco(crear_app):
    def _armar(respuestas=None, *, demora=0.0):
        falso = ClienteDeSalud(respuestas or {}, demora=demora)
        cliente = hacer_cliente(crear_app(cliente_sucursal=falso))
        assert cliente.post("/auth/login", json={"username": "admin", "password": "admin-de-test"}).status_code == 200
        slugs = [f"c{i}" for i in range(1, 6)]
        for slug in slugs:
            alta(cliente, slug)
        asignar_al_admin(cliente, slugs)
        return cliente, falso

    return _armar


def test_sin_sesion_no_se_consulta_nada(client):
    assert client.get("/api/salud").status_code == 401


def test_con_todas_arriba_dice_5_de_5_y_una_fila_por_sucursal(con_cinco):
    cliente, falso = con_cinco({"http://c3:8000": {"version": "v1.2.3"}})

    resp = cliente.get("/api/salud")

    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert (datos["total"], datos["respondieron"]) == (5, 5)
    assert sorted(f["slug"] for f in datos["sucursales"]) == ["c1", "c2", "c3", "c4", "c5"]
    for fila in datos["sucursales"]:
        assert fila["estado"] == "ok"
        assert fila["detalle"] == ""
        assert isinstance(fila["latencia_ms"], int) and fila["latencia_ms"] >= 0
    por_slug = {f["slug"]: f for f in datos["sucursales"]}
    assert por_slug["c3"]["version"] == "v1.2.3"
    assert por_slug["c1"]["version"] is None
    assert sorted(falso.llamadas) == [f"http://c{i}:8000" for i in range(1, 6)]


def test_una_sucursal_caida_figura_caida_con_su_motivo_y_las_otras_siguen_ok(con_cinco):
    """El criterio de aceptación: apagar una instancia a propósito."""
    cliente, _ = con_cinco({"http://c5:8000": SucursalSinRespuesta("ConnectError: se apago")})

    datos = cliente.get("/api/salud").json()

    assert (datos["total"], datos["respondieron"]) == (5, 4)
    caida = next(f for f in datos["sucursales"] if f["slug"] == "c5")
    assert caida["estado"] == "sin_respuesta"
    assert caida["detalle"] == "ConnectError: se apago"
    assert all(f["estado"] == "ok" for f in datos["sucursales"] if f["slug"] != "c5")


def test_una_excepcion_inesperada_degrada_esa_fila_y_no_la_pantalla(con_cinco):
    cliente, _ = con_cinco({"http://c2:8000": KeyError("algo raro")})

    resp = cliente.get("/api/salud")

    assert resp.status_code == 200
    fila = next(f for f in resp.json()["sucursales"] if f["slug"] == "c2")
    assert fila["estado"] == "sin_respuesta"
    assert "KeyError" in fila["detalle"]
    assert resp.json()["respondieron"] == 4


def test_las_cinco_consultas_salen_a_la_vez(con_cinco):
    """Cinco de 0,3 s en serie son 1,5 s; en paralelo, 0,3."""
    cliente, falso = con_cinco(demora=0.3)

    inicio = time.monotonic()
    assert cliente.get("/api/salud").status_code == 200
    transcurrido = time.monotonic() - inicio

    assert transcurrido < 1.0, f"tardo {transcurrido:.2f}s: parece en serie"
    assert len(falso.llamadas) == 5


def test_la_latencia_refleja_lo_que_tardo_cada_una(con_cinco):
    cliente, _ = con_cinco(demora=0.2)
    filas = cliente.get("/api/salud").json()["sucursales"]
    assert all(f["latencia_ms"] >= 190 for f in filas)


def test_el_usuario_solo_ve_la_salud_de_las_sucursales_que_tiene_asignadas(crear_app):
    """🔴 Un cliente no se entera de qué instancias tienen otros."""
    falso = ClienteDeSalud({})
    cliente = hacer_cliente(crear_app(cliente_sucursal=falso))
    cliente.post("/auth/login", json={"username": "admin", "password": "admin-de-test"})
    alta(cliente, "a")
    alta(cliente, "b")
    uno = cliente.post("/api/usuarios", json={
        "username": "uno", "name": "Dueño Uno", "password": "clave-uno", "role": "socio",
    }).json()
    cliente.put("/api/sucursales/a/usuarios", json={"usuario_ids": [int(uno["id"])]})

    otro = hacer_cliente(cliente.app)
    assert otro.post("/auth/login", json={"username": "uno", "password": "clave-uno"}).status_code == 200
    datos = otro.get("/api/salud").json()

    assert [f["slug"] for f in datos["sucursales"]] == ["a"]
    assert (datos["total"], datos["respondieron"]) == (1, 1)
    assert falso.llamadas == ["http://a:8000"]


def test_un_admin_sin_asignaciones_ve_la_salud_vacia(crear_app):
    """Igual que el resumen: no hay una rama para admin que consulte todo."""
    falso = ClienteDeSalud({})
    cliente = hacer_cliente(crear_app(cliente_sucursal=falso))
    cliente.post("/auth/login", json={"username": "admin", "password": "admin-de-test"})
    alta(cliente, "a")

    datos = cliente.get("/api/salud").json()

    assert datos == {"total": 0, "respondieron": 0, "sucursales": []}
    assert falso.llamadas == []


def test_una_sucursal_desactivada_no_se_consulta_ni_cuenta(con_cinco):
    cliente, falso = con_cinco()
    assert cliente.put("/api/sucursales/c5", json={"activa": False}).status_code == 200

    datos = cliente.get("/api/salud").json()

    assert (datos["total"], datos["respondieron"]) == (4, 4)
    assert "http://c5:8000" not in falso.llamadas


def test_una_sucursal_sin_credencial_responde_pero_lo_avisa(crear_app):
    """El `/health` es público: contesta aunque la credencial no esté. El verde no
    puede mentir sobre eso, porque el resumen de esa sucursal va a salir caído."""
    cliente = hacer_cliente(crear_app(cliente_sucursal=ClienteDeSalud({})))
    cliente.post("/auth/login", json={"username": "admin", "password": "admin-de-test"})
    alta(cliente, "con")
    alta(cliente, "sin", credencial="")
    asignar_al_admin(cliente, ["con", "sin"])

    filas = {f["slug"]: f for f in cliente.get("/api/salud").json()["sucursales"]}

    assert filas["con"]["tiene_credencial"] is True
    assert filas["sin"]["tiene_credencial"] is False
    assert filas["sin"]["estado"] == "ok"


def test_la_respuesta_no_lleva_credenciales_ni_urls(con_cinco):
    cliente, _ = con_cinco()
    texto = cliente.get("/api/salud").text
    assert "cred-secreta" not in texto
    assert "http://" not in texto


def test_nada_se_cachea(con_cinco):
    cliente, _ = con_cinco()
    assert cliente.get("/api/salud").headers["cache-control"] == "no-store"


def test_el_panel_real_de_punta_a_punta_contra_una_instancia_viva_y_una_con_spa(crear_app):
    """Sin doble de cliente: el `ClienteSucursal` de verdad por ASGITransport.

    Una instancia sana y otra cuya `url_base` apunta a un catch-all de SPA. Es lo
    que prueba que el router y el cliente reales dicen «4 de 5» y no «5 de 5»."""
    sana = instancia({"ok": True, "product": "contalibra"})
    spa = FastAPI()

    @spa.get("/{ruta:path}", include_in_schema=False)
    def catch_all(ruta: str):
        return HTMLResponse(HTML_DE_LA_SPA)

    class Enrutador(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            app = sana if request.url.host == "sana" else spa
            return await httpx.ASGITransport(app=app).handle_async_request(request)

    cliente_real = ClienteSucursal(timeout=2.0, timeout_salud=2.0, transport=Enrutador())
    cliente = hacer_cliente(crear_app(cliente_sucursal=cliente_real))
    cliente.post("/auth/login", json={"username": "admin", "password": "admin-de-test"})
    alta(cliente, "sana")
    alta(cliente, "equivocada")
    asignar_al_admin(cliente, ["sana", "equivocada"])

    datos = cliente.get("/api/salud").json()

    assert (datos["total"], datos["respondieron"]) == (2, 1)
    filas = {f["slug"]: f for f in datos["sucursales"]}
    assert filas["sana"]["estado"] == "ok"
    assert filas["equivocada"]["estado"] == "sin_respuesta"
    assert "SPA" in filas["equivocada"]["detalle"]
