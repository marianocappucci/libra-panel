"""El cliente HTTP contra una sucursal, con el router y el guard reales.

Lo que se prueba aca es el **contrato de cable**: que el panel mande la
credencial en el header que la sucursal mira, en la ruta que la sucursal
expone, y que sepa distinguir una respuesta buena de las cuatro formas en que
una sucursal puede contestar algo que no sirve.
"""
import httpx
import pytest

from libra_panel.cliente_sucursal import (
    HEADER_CREDENCIAL, RUTA_RESUMEN, ClienteSucursal, SucursalSinRespuesta,
)

from .sucursal_falsa import (
    HTML_DE_LA_SPA, NUCLEO_TIPICO, crear_sucursal_falsa, crear_sucursal_que_contesta,
)

CREDENCIAL = "credencial-de-la-sucursal-uno"


def cliente_contra(app, *, timeout: float = 5.0) -> ClienteSucursal:
    return ClienteSucursal(timeout=timeout, transport=httpx.ASGITransport(app=app))


@pytest.fixture
def con_credencial(monkeypatch):
    """La sucursal tiene su `LIBRA_PANEL_TOKEN` seteado, como en el compose."""
    monkeypatch.setenv("LIBRA_PANEL_TOKEN", CREDENCIAL)


async def pedir(cliente, **kw):
    return await cliente.resumen(
        url_base=kw.pop("url_base", "http://sucursal"),
        credencial=kw.pop("credencial", CREDENCIAL),
        desde=kw.pop("desde", "2026-08-01"),
        hasta=kw.pop("hasta", "2026-08-20"),
    )


@pytest.mark.anyio
async def test_la_credencial_correcta_trae_el_nucleo(monkeypatch, con_credencial):
    app = crear_sucursal_falsa(monkeypatch)
    datos = await pedir(cliente_contra(app))

    assert datos["nucleo"] == NUCLEO_TIPICO
    assert datos["instancia"]["cuit"] == "30-71234567-9"
    assert datos["periodo"] == {"desde": "2026-08-01", "hasta": "2026-08-20"}


@pytest.mark.anyio
async def test_el_bloque_que_el_producto_manda_llega_y_el_que_no_no_esta(monkeypatch, con_credencial):
    comercio = {"ventas": {"cantidad": 7, "monto": 700.0}, "stock_bajo_minimo": 3}
    app = crear_sucursal_falsa(monkeypatch, bloques={"comercio": comercio})
    datos = await pedir(cliente_contra(app))

    assert datos["comercio"] == comercio
    # Un producto sin LibraGenda no manda `agenda`. No viene en cero: no viene.
    assert "agenda" not in datos


@pytest.mark.anyio
async def test_sin_agenda_el_producto_no_la_manda(monkeypatch, con_credencial):
    app = crear_sucursal_falsa(monkeypatch, bloques={})
    datos = await pedir(cliente_contra(app))
    assert set(datos) == {"instancia", "periodo", "nucleo"}


@pytest.mark.anyio
async def test_la_credencial_equivocada_no_pasa(monkeypatch, con_credencial):
    app = crear_sucursal_falsa(monkeypatch)
    with pytest.raises(SucursalSinRespuesta) as exc:
        await pedir(cliente_contra(app), credencial="otra-cosa")
    assert "401" in exc.value.detalle


@pytest.mark.anyio
async def test_sin_credencial_se_corta_antes_de_salir_a_la_red(monkeypatch, con_credencial):
    """El detalle tiene que decir que falta cargarla, no "no autenticado".

    Un 401 se lee como credencial equivocada. Lo cierto es que el alta de esa
    sucursal quedo a medias, y es otra cosa la que hay que ir a arreglar.
    """
    app = crear_sucursal_falsa(monkeypatch)
    with pytest.raises(SucursalSinRespuesta) as exc:
        await pedir(cliente_contra(app), credencial="")
    assert "no tiene credencial cargada" in exc.value.detalle


@pytest.mark.anyio
async def test_una_sucursal_sin_LIBRA_PANEL_TOKEN_rechaza(monkeypatch):
    """Opt-in por ausencia: sin la variable, el guard ni mira el header.

    Es el estado real medido en el VPS el 2026-08-20: las dos instancias de
    Contalibra exponen `/api/resumen` y ninguna tiene la variable puesta. El
    panel tiene que decir que no puede entrar, no sumar cero.
    """
    monkeypatch.delenv("LIBRA_PANEL_TOKEN", raising=False)
    app = crear_sucursal_falsa(monkeypatch)
    with pytest.raises(SucursalSinRespuesta) as exc:
        await pedir(cliente_contra(app))
    assert "401" in exc.value.detalle


# ── Las cuatro formas de contestar algo que no sirve ─────────────────────────


@pytest.mark.anyio
async def test_el_catch_all_de_la_SPA_no_pasa_por_exito(monkeypatch, con_credencial):
    """🔴 El modo de fallo que produciria el cero mas caro del panel.

    Una sucursal con el motor viejo —sin el router de resumen— no da 404: da
    **200 con el index.html**, porque los seis productos de la familia sirven
    su SPA con fallback. Medido el 2026-08-20 contra `contalibra`: una ruta
    inventada devuelve 200 `text/html`.

    Si el cliente se conformara con el codigo de estado, leeria HTML como exito
    y esa sucursal entraria al consolidado como una que vendio cero.
    """
    app = crear_sucursal_que_contesta(HTML_DE_LA_SPA)
    with pytest.raises(SucursalSinRespuesta) as exc:
        await pedir(cliente_contra(app))
    assert "fallback de la SPA" in exc.value.detalle


@pytest.mark.anyio
async def test_un_json_que_no_es_objeto_no_pasa(monkeypatch, con_credencial):
    app = crear_sucursal_que_contesta([1, 2, 3])
    with pytest.raises(SucursalSinRespuesta) as exc:
        await pedir(cliente_contra(app))
    assert "objeto JSON" in exc.value.detalle


@pytest.mark.anyio
async def test_un_json_sin_nucleo_no_pasa(monkeypatch, con_credencial):
    """El nucleo lo tienen los seis productos: sale de LibraCore."""
    app = crear_sucursal_que_contesta({"instancia": {}, "periodo": {}})
    with pytest.raises(SucursalSinRespuesta) as exc:
        await pedir(cliente_contra(app))
    assert "'nucleo'" in exc.value.detalle


@pytest.mark.anyio
async def test_un_500_de_la_sucursal_se_reporta_con_su_codigo(monkeypatch, con_credencial):
    app = crear_sucursal_que_contesta(None, status=500)
    with pytest.raises(SucursalSinRespuesta) as exc:
        await pedir(cliente_contra(app))
    assert "HTTP 500" in exc.value.detalle


@pytest.mark.anyio
async def test_una_sucursal_que_no_resuelve_es_sin_respuesta_y_no_un_500_del_panel():
    """Un DNS que no resuelve es informacion sobre esa sucursal, no una falla."""
    cliente = ClienteSucursal(timeout=1.0)
    with pytest.raises(SucursalSinRespuesta) as exc:
        await pedir(cliente, url_base="http://esta-sucursal-no-existe.invalid")
    assert exc.value.detalle


# ── Contrato de cable ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_manda_el_header_y_las_fechas_que_espera_la_sucursal(monkeypatch, con_credencial):
    """Se mira el pedido tal cual sale, no lo que el cliente cree que mando."""
    visto = {}

    async def espiar(request: httpx.Request) -> httpx.Response:
        visto["url"] = str(request.url)
        visto["header"] = request.headers.get(HEADER_CREDENCIAL)
        return httpx.Response(200, json={"nucleo": {}, "instancia": {}, "periodo": {}})

    cliente = ClienteSucursal(timeout=5.0, transport=httpx.MockTransport(espiar))
    await pedir(cliente, url_base="http://contalibra:8000/")

    # La barra de mas del `url_base` no duplica la barra de la ruta.
    assert visto["url"] == f"http://contalibra:8000{RUTA_RESUMEN}?desde=2026-08-01&hasta=2026-08-20"
    assert visto["header"] == CREDENCIAL


@pytest.mark.anyio
async def test_el_timeout_corta_y_lo_dice():
    async def colgarse(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("se colgo", request=request)

    cliente = ClienteSucursal(timeout=0.1, transport=httpx.MockTransport(colgarse))
    with pytest.raises(SucursalSinRespuesta) as exc:
        await pedir(cliente)
    assert "ReadTimeout" in exc.value.detalle
