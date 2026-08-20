"""`GET /api/resumen`: las N llamadas en paralelo y la sucursal que no contesta.

El test que importa de este archivo es
`test_una_sucursal_caida_da_4_de_5_y_no_un_total_mas_chico`: es el criterio de
aceptacion escrito en la Fase 2 del plan —"apagando una instancia a proposito,
el panel tiene que decir 4 de 5 y **no** mostrar un total mas chico como si
fuera el bueno"—.
"""
import asyncio
import time

import pytest
from .conftest import hacer_cliente

from libra_panel.cliente_sucursal import SucursalSinRespuesta

NUCLEO = {"facturado": 100.0, "cobrado": 90.0, "sin_cobrar": {"cantidad": 1, "monto": 10.0}}


class ClienteFalso:
    """Contesta segun la `url_base`, y puede tardar o caerse por sucursal.

    Se dobla el cliente y no cada sucursal porque lo que se prueba aca es el
    router: que lance las N a la vez, que ninguna caida arrastre a las otras y
    que la respuesta diga de cuantas salio. El contrato de cable contra una
    sucursal real esta probado en `test_cliente_sucursal.py`, contra el router
    de verdad de LibraCore.
    """

    def __init__(self, respuestas: dict, *, demora: float = 0.0):
        self.respuestas = respuestas
        self.demora = demora
        self.llamadas = []

    async def resumen(self, *, url_base, credencial, desde, hasta):
        self.llamadas.append((url_base, desde, hasta))
        if self.demora:
            await asyncio.sleep(self.demora)
        valor = self.respuestas[url_base]
        if isinstance(valor, Exception):
            raise valor
        return valor


def cuerpo(*, cuit="30-71234567-9", nombre="Sucursal", **bloques):
    return {
        "instancia": {"nombre": nombre, "cuit": cuit, "punto_venta": 1},
        "periodo": {"desde": "2026-08-01", "hasta": "2026-08-20"},
        "nucleo": dict(NUCLEO),
        **bloques,
    }


def alta(cliente_admin, slug, *, url=None, cuit="30-71234567-9", razon_social="Padel SA"):
    resp = cliente_admin.post("/api/sucursales", json={
        "slug": slug, "nombre": slug.title(), "url_base": url or f"http://{slug}:8000",
        "cuit": cuit, "razon_social": razon_social, "credencial": f"cred-{slug}",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def asignar_todas_al_admin(cliente_admin, slugs):
    uid = int(cliente_admin.get("/auth/me").json()["id"])
    for slug in slugs:
        resp = cliente_admin.put(f"/api/sucursales/{slug}/usuarios", json={"usuario_ids": [uid]})
        assert resp.status_code == 200, resp.text


@pytest.fixture
def con_cinco(crear_app):
    """Cinco sucursales asignadas al admin, con un cliente falso configurable."""

    def _armar(respuestas, *, demora=0.0):
        falso = ClienteFalso(respuestas, demora=demora)
        app = crear_app(cliente_sucursal=falso)
        cliente = hacer_cliente(app)
        resp = cliente.post("/auth/login", json={"username": "admin", "password": "admin-de-test"})
        assert resp.status_code == 200, resp.text
        for slug in respuestas:
            alta(cliente, slug.removeprefix("http://").removesuffix(":8000"), url=slug)
        asignar_todas_al_admin(
            cliente, [s.removeprefix("http://").removesuffix(":8000") for s in respuestas]
        )
        return cliente, falso

    return _armar


# ── El criterio de aceptacion ───────────────────────────────────────────────


def test_una_sucursal_caida_da_4_de_5_y_no_un_total_mas_chico(con_cinco):
    """🔴 El test que define si el panel sirve o miente.

    Cuatro sucursales contestan 100 cada una. La quinta esta caida. El total es
    400 — y lo que no puede pasar es que 400 se presente como el total de las
    cinco.
    """
    respuestas = {f"http://c{i}:8000": cuerpo(nombre=f"C{i}") for i in range(1, 5)}
    respuestas["http://c5:8000"] = SucursalSinRespuesta("ConnectTimeout: se apago")
    cliente, _ = con_cinco(respuestas)

    datos = cliente.get("/api/resumen").json()

    assert datos["cobertura"]["total"] == 5
    assert datos["cobertura"]["respondieron"] == 4
    assert datos["cobertura"]["parcial"] is True
    assert [s["slug"] for s in datos["cobertura"]["sin_respuesta"]] == ["c5"]
    assert "ConnectTimeout" in datos["cobertura"]["sin_respuesta"][0]["detalle"]
    assert datos["consolidado"]["nucleo"]["datos"]["facturado"] == 400.0
    assert datos["consolidado"]["nucleo"]["sucursales"] == 4

    # Y la fila de la caida esta, nombrada, en vez de desaparecer de la lista.
    caida = next(s for s in datos["sucursales"] if s["slug"] == "c5")
    assert caida["estado"] == "sin_respuesta"
    assert caida["bloques"] == {}


def test_con_todas_arriba_el_total_no_queda_marcado_parcial(con_cinco):
    """Control positivo: si `parcial` fuera siempre True el test de arriba
    pasaria igual y no probaria nada."""
    respuestas = {f"http://c{i}:8000": cuerpo() for i in range(1, 6)}
    cliente, _ = con_cinco(respuestas)

    datos = cliente.get("/api/resumen").json()
    assert datos["cobertura"] == {
        "total": 5, "respondieron": 5, "parcial": False, "sin_respuesta": [],
    }
    assert datos["consolidado"]["nucleo"]["datos"]["facturado"] == 500.0


def test_todas_caidas_no_es_un_total_en_cero(con_cinco):
    """El peor caso: si el consolidado saliera con `facturado: 0` seria un cero
    perfectamente creible."""
    respuestas = {f"http://c{i}:8000": SucursalSinRespuesta("caida") for i in range(1, 6)}
    cliente, _ = con_cinco(respuestas)

    datos = cliente.get("/api/resumen").json()
    assert datos["cobertura"]["respondieron"] == 0
    # No hay bloque nucleo: no hay de donde sacarlo. Un `{"facturado": 0}` seria
    # una invencion.
    assert datos["consolidado"] == {}


# ── En paralelo, no en serie ────────────────────────────────────────────────


def test_las_cinco_llamadas_salen_a_la_vez(con_cinco):
    """Cinco de 0,3 s en serie son 1,5 s; en paralelo, 0,3.

    Se mide el tiempo de pared porque es lo unico que distingue de verdad las
    dos formas: contar llamadas da 5 en los dos casos.
    """
    respuestas = {f"http://c{i}:8000": cuerpo() for i in range(1, 6)}
    cliente, _ = con_cinco(respuestas, demora=0.3)

    arranque = time.monotonic()
    assert cliente.get("/api/resumen").status_code == 200
    transcurrido = time.monotonic() - arranque

    # Holgado a proposito: lo que se descarta es "en serie" (>= 1,5 s), no que
    # tarde exactamente 0,3.
    assert transcurrido < 1.0, f"tardo {transcurrido:.2f}s: parece en serie"


def test_una_sucursal_lenta_no_retrasa_a_las_demas_mas_que_ella_misma(con_cinco):
    """Con las N a la vez, el reloj lo marca la mas lenta y no la suma."""
    respuestas = {f"http://c{i}:8000": cuerpo() for i in range(1, 6)}
    cliente, falso = con_cinco(respuestas, demora=0.2)
    arranque = time.monotonic()
    cliente.get("/api/resumen")
    assert time.monotonic() - arranque < 0.8
    assert len(falso.llamadas) == 5


# ── Alcance por usuario ─────────────────────────────────────────────────────


def test_el_usuario_solo_ve_las_sucursales_que_tiene_asignadas(crear_app):
    """🔴 El aislamiento entre clientes. No hay una rama para admin.

    Dos duenos en el mismo panel: cada uno tiene que ver su total, no la suma
    de los dos.
    """
    falso = ClienteFalso({
        "http://a:8000": cuerpo(cuit="30-11111111-9"),
        "http://b:8000": cuerpo(cuit="30-22222222-9"),
    })
    cliente = hacer_cliente(crear_app(cliente_sucursal=falso))
    cliente.post("/auth/login", json={"username": "admin", "password": "admin-de-test"})
    alta(cliente, "a", url="http://a:8000", cuit="30-11111111-9", razon_social="Dueño Uno")
    alta(cliente, "b", url="http://b:8000", cuit="30-22222222-9", razon_social="Dueño Dos")

    uno = cliente.post("/api/usuarios", json={
        "username": "uno", "name": "Dueño Uno", "password": "clave-uno", "role": "socio",
    }).json()
    cliente.put("/api/sucursales/a/usuarios", json={"usuario_ids": [int(uno["id"])]})

    otro = hacer_cliente(cliente.app)
    otro.post("/auth/login", json={"username": "uno", "password": "clave-uno"})
    datos = otro.get("/api/resumen").json()

    assert datos["cobertura"]["total"] == 1
    assert [s["slug"] for s in datos["sucursales"]] == ["a"]
    assert datos["consolidado"]["nucleo"]["datos"]["facturado"] == 100.0


def test_un_admin_sin_asignaciones_ve_el_panel_vacio(crear_app):
    """Y esta bien: sumar las sucursales de clientes distintos no significa nada."""
    falso = ClienteFalso({"http://a:8000": cuerpo()})
    cliente = hacer_cliente(crear_app(cliente_sucursal=falso))
    cliente.post("/auth/login", json={"username": "admin", "password": "admin-de-test"})
    alta(cliente, "a", url="http://a:8000")

    datos = cliente.get("/api/resumen").json()
    assert datos["cobertura"]["total"] == 0
    assert datos["consolidado"] == {}
    assert falso.llamadas == []


def test_una_sucursal_desactivada_no_se_consulta_ni_cuenta(con_cinco):
    respuestas = {f"http://c{i}:8000": cuerpo() for i in range(1, 6)}
    cliente, falso = con_cinco(respuestas)
    assert cliente.put("/api/sucursales/c5", json={"activa": False}).status_code == 200

    datos = cliente.get("/api/resumen").json()
    # 4 de 4, no 4 de 5: el dueño cerro ese local, no es que no conteste.
    assert datos["cobertura"] == {
        "total": 4, "respondieron": 4, "parcial": False, "sin_respuesta": [],
    }
    assert len(falso.llamadas) == 4


def test_sin_sesion_no_se_consulta_nada(client):
    assert client.get("/api/resumen").status_code == 401


# ── Periodo y caché ─────────────────────────────────────────────────────────


def test_el_periodo_se_le_reenvia_tal_cual_a_cada_sucursal(con_cinco):
    cliente, falso = con_cinco({"http://c1:8000": cuerpo()})
    cliente.get("/api/resumen?desde=2026-07-01&hasta=2026-07-31")
    assert falso.llamadas == [("http://c1:8000", "2026-07-01", "2026-07-31")]


def test_sin_periodo_se_pide_el_mes_en_curso(con_cinco):
    from libra_panel.fechas import rango_por_defecto

    cliente, falso = con_cinco({"http://c1:8000": cuerpo()})
    cliente.get("/api/resumen")
    assert falso.llamadas[0][1:] == rango_por_defecto()


@pytest.mark.parametrize("query", ["desde=ayer", "hasta=32-13-2026", "desde=2026-08-20&hasta=2026-08-01"])
def test_un_periodo_invalido_da_422_y_no_sale_a_la_red(con_cinco, query):
    cliente, falso = con_cinco({"http://c1:8000": cuerpo()})
    assert cliente.get(f"/api/resumen?{query}").status_code == 422
    assert falso.llamadas == []


def test_la_respuesta_no_se_cachea(con_cinco):
    """🔴 En vivo y cacheado se contradicen, y un parcial cacheado es peor:
    se queda pegado despues de que la sucursal volvio."""
    cliente, _ = con_cinco({"http://c1:8000": cuerpo()})
    resp = cliente.get("/api/resumen")
    assert resp.headers["cache-control"] == "no-store"


def test_dos_consultas_seguidas_vuelven_a_preguntar(con_cinco):
    """Control del anterior: la cabecera podria estar y el panel cachear igual
    del lado del servidor."""
    cliente, falso = con_cinco({"http://c1:8000": cuerpo()})
    cliente.get("/api/resumen")
    cliente.get("/api/resumen")
    assert len(falso.llamadas) == 2


# ── Errores raros de una sucursal ───────────────────────────────────────────


def test_un_error_inesperado_de_una_sucursal_degrada_su_fila_y_nada_mas(con_cinco):
    cliente, _ = con_cinco({
        "http://c1:8000": cuerpo(),
        "http://c2:8000": RuntimeError("algo rarisimo"),
    })
    datos = cliente.get("/api/resumen").json()
    assert datos["cobertura"]["respondieron"] == 1
    caida = next(s for s in datos["sucursales"] if s["slug"] == "c2")
    assert "RuntimeError" in caida["detalle"]


def test_una_sucursal_sin_credencial_lo_dice_antes_de_salir_a_la_red(crear_app):
    falso = ClienteFalso({"http://a:8000": cuerpo()})
    cliente = hacer_cliente(crear_app(cliente_sucursal=falso))
    cliente.post("/auth/login", json={"username": "admin", "password": "admin-de-test"})
    cliente.post("/api/sucursales", json={
        "slug": "a", "nombre": "A", "url_base": "http://a:8000", "credencial": "",
    })
    uid = int(cliente.get("/auth/me").json()["id"])
    cliente.put("/api/sucursales/a/usuarios", json={"usuario_ids": [uid]})

    datos = cliente.get("/api/resumen").json()
    assert datos["cobertura"]["respondieron"] == 0
    assert "no tiene credencial cargada" in datos["sucursales"][0]["detalle"]
    assert falso.llamadas == []
