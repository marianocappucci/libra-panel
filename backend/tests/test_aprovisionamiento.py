"""El alta de un empleado en varias sucursales: el cable y la orquestacion.

Dos mitades, y estan separadas a proposito:

- **El cable** (`crear_usuario`) se prueba contra una sucursal falsa con el
  guard **real** de libraauth. Lo que se mide es que el panel mande la
  credencial en el header que la sucursal mira, a la ruta que la sucursal
  expone, y que sepa distinguir un alta de algo que no lo es.
- **La orquestacion** (`POST /api/empleados`) se prueba con un doble del
  cliente, igual que `test_resumen.py`: lo que importa ahi es que salgan las N
  a la vez, que una caida no arrastre a las otras y que el alcance sea el del
  usuario. Meter sucursales de verdad ahi no agregaria nada y ademas no se
  puede: `token_de_panel_valido` lee UNA variable de entorno, asi que dos
  sucursales falsas no pueden tener credenciales validas distintas a la vez.
"""
import asyncio

import httpx
import pytest
from sqlalchemy import text

from libra_panel import db
from libra_panel.cliente_sucursal import (
    ClienteSucursal,
    EmpleadoYaExiste,
    SucursalSinRespuesta,
)

from .conftest import hacer_cliente
from .sucursal_falsa import (
    HTML_DE_LA_SPA,
    crear_sucursal_de_empleados,
    crear_sucursal_que_contesta_al_alta,
)

CREDENCIAL = "credencial-de-la-sucursal-uno"
CONTRASENA = "una-contrasena-larga-de-empleado"


def cliente_contra(app, *, timeout: float = 5.0) -> ClienteSucursal:
    return ClienteSucursal(timeout=timeout, transport=httpx.ASGITransport(app=app))


@pytest.fixture
def con_credencial(monkeypatch):
    """La sucursal tiene su `LIBRA_PANEL_TOKEN` seteado, como en el compose."""
    monkeypatch.setenv("LIBRA_PANEL_TOKEN", CREDENCIAL)


DATOS = {
    "username": "sofia", "name": "Sofia Diaz",
    "password": CONTRASENA, "role": "staff",
}


async def dar_de_alta(cliente, **kw):
    return await cliente.crear_usuario(
        url_base=kw.pop("url_base", "http://sucursal"),
        credencial=kw.pop("credencial", CREDENCIAL),
        ruta=kw.pop("ruta", "/api/usuarios"),
        datos=kw.pop("datos", dict(DATOS)),
    )


# --------------------------------------------------------------- el cable ---


@pytest.mark.anyio
async def test_la_credencial_correcta_da_de_alta(con_credencial):
    recibidas = []
    app = crear_sucursal_de_empleados(recibidas=recibidas)

    creado = await dar_de_alta(cliente_contra(app))

    assert creado["username"] == "sofia"
    assert creado["name"] == "Sofia Diaz"
    # Lo que la sucursal recibio es lo que el panel dijo mandar, la contrasena
    # incluida: es la unica forma de que el empleado pueda entrar despues.
    assert recibidas == [DATOS]


@pytest.mark.anyio
async def test_la_credencial_equivocada_no_da_de_alta_a_nadie(con_credencial):
    recibidas = []
    app = crear_sucursal_de_empleados(recibidas=recibidas)

    with pytest.raises(SucursalSinRespuesta):
        await dar_de_alta(cliente_contra(app), credencial="otra-cosa")

    # 🔑 El control que hace que este test valga: no alcanza con que el panel
    # levante la excepcion, tiene que ser porque la sucursal NO creo nada. Sin
    # esto pasaria igual un guard que crea el usuario y despues contesta 401.
    assert recibidas == []


@pytest.mark.anyio
async def test_sin_credencial_cargada_ni_sale_a_la_red(con_credencial):
    recibidas = []
    app = crear_sucursal_de_empleados(recibidas=recibidas)

    with pytest.raises(SucursalSinRespuesta) as e:
        await dar_de_alta(cliente_contra(app), credencial="")

    # 🔑 El mensaje propio del panel, no un "credencial" cualquiera: la sede
    # tambien contesta "credencial de panel invalida" cuando el header va
    # vacio, asi que un assert flojo se cumple igual sin el chequeo previo y el
    # test no prueba nada. Medido: es lo unico que separa los dos caminos.
    assert "no tiene credencial cargada en el panel" in str(e.value)
    assert recibidas == []


@pytest.mark.anyio
async def test_un_409_es_ya_existe_y_no_una_falla(con_credencial):
    app = crear_sucursal_de_empleados(ya_existen=("sofia",))

    with pytest.raises(EmpleadoYaExiste):
        await dar_de_alta(cliente_contra(app))


@pytest.mark.anyio
async def test_la_ruta_viaja_y_no_se_asume(con_credencial):
    """Una sucursal de las tres que exponen `/users` y no `/api/usuarios`."""
    recibidas = []
    app = crear_sucursal_de_empleados(ruta="/users", recibidas=recibidas)

    creado = await dar_de_alta(cliente_contra(app), ruta="/users")

    assert creado["username"] == "sofia"
    assert len(recibidas) == 1


@pytest.mark.anyio
async def test_la_ruta_equivocada_falla_y_no_crea_a_nadie(con_credencial):
    """El caso de una sucursal de `/users` cargada con la ruta de la mayoria.

    ⚠️ Da 405 y **no** 200 con el HTML de la SPA: el catch-all de los ocho
    productos es `@app.get`. Lo importante es lo de abajo ---que nadie quedo
    creado---, no el codigo exacto.
    """
    recibidas = []
    app = crear_sucursal_de_empleados(ruta="/users", recibidas=recibidas)

    with pytest.raises(SucursalSinRespuesta):
        await dar_de_alta(cliente_contra(app), ruta="/api/usuarios")

    assert recibidas == []


@pytest.mark.anyio
async def test_un_2xx_que_no_trae_un_usuario_no_se_toma_por_bueno():
    """Lo que `_usuario_valido` esta ahi para atajar.

    Una sede que contesta 200 con cualquier otra cosa ---un `url_base` apuntado
    a otro contenedor de la red de control--- no puede leerse como un alta: el
    dueño se enteraria el dia que el empleado no puede entrar.
    """
    app = crear_sucursal_que_contesta_al_alta({"ok": True})

    with pytest.raises(SucursalSinRespuesta) as e:
        await dar_de_alta(cliente_contra(app))

    assert "usuario" in str(e.value).lower()


@pytest.mark.anyio
async def test_un_2xx_con_html_tampoco():
    app = crear_sucursal_que_contesta_al_alta(HTML_DE_LA_SPA)

    with pytest.raises(SucursalSinRespuesta) as e:
        await dar_de_alta(cliente_contra(app))

    assert "json" in str(e.value).lower()


# -------------------------------------------------------- la orquestacion ---


class ClienteFalso:
    """Contesta el alta segun la `url_base`. Doble del cliente, no del cable."""

    def __init__(self, respuestas: dict, *, demora: float = 0.0):
        self.respuestas = respuestas
        self.demora = demora
        self.altas = []

    async def crear_usuario(self, *, url_base, credencial, ruta, datos):
        self.altas.append((url_base, ruta, credencial, dict(datos)))
        if self.demora:
            await asyncio.sleep(self.demora)
        valor = self.respuestas[url_base]
        if isinstance(valor, Exception):
            raise valor
        return valor


def alta_de_sucursal(admin, slug, *, ruta="/api/usuarios"):
    resp = admin.post("/api/sucursales", json={
        "slug": slug, "nombre": slug.title(), "url_base": f"http://{slug}:8000",
        "cuit": "30-71234567-9", "razon_social": "Padel SA",
        "credencial": f"cred-{slug}", "ruta_de_usuarios": ruta,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def con_dos(crear_app):
    """Dos sucursales asignadas al admin, con un cliente falso configurable."""

    def _armar(respuestas, *, rutas=None, asignar=True):
        falso = ClienteFalso(respuestas)
        app = crear_app(cliente_sucursal=falso)
        cliente = hacer_cliente(app)
        resp = cliente.post(
            "/auth/login", json={"username": "admin", "password": "admin-de-test"}
        )
        assert resp.status_code == 200, resp.text
        slugs = [u.removeprefix("http://").removesuffix(":8000") for u in respuestas]
        for slug in slugs:
            alta_de_sucursal(cliente, slug, ruta=(rutas or {}).get(slug, "/api/usuarios"))
        if asignar:
            uid = int(cliente.get("/auth/me").json()["id"])
            for slug in slugs:
                r = cliente.put(
                    f"/api/sucursales/{slug}/usuarios", json={"usuario_ids": [uid]}
                )
                assert r.status_code == 200, r.text
        return cliente, falso, slugs

    return _armar


def creado(username="sofia"):
    return {"id": 1, "username": username, "name": "Sofia Diaz", "role": "staff"}


PEDIDO = {
    "username": "sofia", "name": "Sofia Diaz",
    "password": CONTRASENA, "role": "staff",
}


def test_el_alta_en_dos_sedes_sale_en_las_dos(con_dos):
    cliente, falso, slugs = con_dos({
        "http://uno:8000": creado(), "http://dos:8000": creado(),
    })

    resp = cliente.post("/api/empleados", json={**PEDIDO, "slugs": slugs})

    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["parcial"] is False
    assert [f["estado"] for f in cuerpo["sucursales"]] == ["creado", "creado"]
    assert {f["slug"] for f in cuerpo["sucursales"]} == set(slugs)
    # Cada sede recibio SU credencial, no la de la otra.
    assert sorted(c for _, _, c, _ in falso.altas) == ["cred-dos", "cred-uno"]


def test_una_sede_caida_no_arrastra_a_la_otra(con_dos):
    cliente, falso, slugs = con_dos({
        "http://uno:8000": creado(),
        "http://dos:8000": SucursalSinRespuesta("ConnectError: se cayo"),
    })

    resp = cliente.post("/api/empleados", json={**PEDIDO, "slugs": slugs})

    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    # 🔑 El criterio: el empleado queda dado de alta en la que si contesta. Un
    # 500 acá lo dejaria sin usuario en NINGUNA de las dos.
    assert cuerpo["parcial"] is True
    por_slug = {f["slug"]: f for f in cuerpo["sucursales"]}
    assert por_slug["uno"]["estado"] == "creado"
    assert por_slug["dos"]["estado"] == "sin_respuesta"
    assert "se cayo" in por_slug["dos"]["detalle"]


def test_donde_ya_trabajaba_dice_ya_estaba_y_no_es_una_falla(con_dos):
    cliente, falso, slugs = con_dos({
        "http://uno:8000": EmpleadoYaExiste("Ya existe un usuario con ese nombre."),
        "http://dos:8000": creado(),
    })

    resp = cliente.post("/api/empleados", json={**PEDIDO, "slugs": slugs})

    cuerpo = resp.json()
    por_slug = {f["slug"]: f for f in cuerpo["sucursales"]}
    assert por_slug["uno"]["estado"] == "ya_estaba"
    assert por_slug["dos"]["estado"] == "creado"
    # No es una falla: la pantalla no lo pinta de rojo y no hay nada que
    # reintentar.
    assert cuerpo["parcial"] is False


def test_una_sucursal_que_no_tengo_asignada_frena_el_pedido_entero(con_dos):
    cliente, falso, slugs = con_dos(
        {"http://uno:8000": creado(), "http://dos:8000": creado()}, asignar=False
    )

    resp = cliente.post("/api/empleados", json={**PEDIDO, "slugs": slugs})

    assert resp.status_code == 409, resp.text
    # 🔑 Y no se dio de alta en NINGUNA. Un alta a medias es peor que ninguna
    # porque parece aplicada.
    assert falso.altas == []


def test_lo_que_no_pedi_no_se_da_de_alta(con_dos):
    cliente, falso, slugs = con_dos({
        "http://uno:8000": creado(), "http://dos:8000": creado(),
    })

    resp = cliente.post("/api/empleados", json={**PEDIDO, "slugs": ["uno"]})

    assert resp.status_code == 200, resp.text
    assert [f["slug"] for f in resp.json()["sucursales"]] == ["uno"]
    assert [u for u, _, _, _ in falso.altas] == ["http://uno:8000"]


def test_la_ruta_de_cada_sucursal_es_la_que_viaja(con_dos):
    cliente, falso, slugs = con_dos(
        {"http://uno:8000": creado(), "http://dos:8000": creado()},
        rutas={"dos": "/users"},
    )

    cliente.post("/api/empleados", json={**PEDIDO, "slugs": slugs})

    rutas = {u: r for u, r, _, _ in falso.altas}
    assert rutas == {"http://uno:8000": "/api/usuarios", "http://dos:8000": "/users"}


def test_la_ruta_se_guarda_en_una_sola_forma(crear_app):
    """`users`, `/users` y `/users/` son la misma ruta.

    Sin normalizar quedan tres textos distintos para lo mismo. No rompe el
    alta ---el cliente arma la URL con su propia barra--- pero deja la pantalla
    mostrando lo que se tipeo y cualquier comparacion entre sucursales dando
    distinto.
    """
    cliente = hacer_cliente(crear_app())
    r = cliente.post(
        "/auth/login", json={"username": "admin", "password": "admin-de-test"}
    )
    assert r.status_code == 200, r.text

    for i, tipeada in enumerate(("users", "/users", "/users/")):
        resp = cliente.post("/api/sucursales", json={
            "slug": f"sede{i}", "nombre": f"Sede {i}",
            "url_base": f"http://sede{i}:8000", "credencial": "x",
            "ruta_de_usuarios": tipeada,
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["ruta_de_usuarios"] == "/users", tipeada

    # Y editandola despues, que es el otro camino por el que entra.
    resp = cliente.put("/api/sucursales/sede0", json={"ruta_de_usuarios": "api/usuarios/"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ruta_de_usuarios"] == "/api/usuarios"

    # Vacia vuelve al default y no a "/": una sucursal sin ruta cargada no
    # apunta a la raiz del producto.
    resp = cliente.put("/api/sucursales/sede0", json={"ruta_de_usuarios": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ruta_de_usuarios"] == "/api/usuarios"


def test_sin_sesion_no_se_da_de_alta_a_nadie(con_dos):
    cliente, falso, slugs = con_dos({
        "http://uno:8000": creado(), "http://dos:8000": creado(),
    })
    cliente.post("/auth/logout")

    resp = cliente.post("/api/empleados", json={**PEDIDO, "slugs": slugs})

    assert resp.status_code == 401, resp.text
    assert falso.altas == []


def test_un_socio_no_aprovisiona(con_dos):
    cliente, falso, slugs = con_dos({
        "http://uno:8000": creado(), "http://dos:8000": creado(),
    })
    r = cliente.post("/api/usuarios", json={
        "username": "socio", "name": "Un Socio",
        "password": "contrasena-del-socio", "role": "socio",
    })
    assert r.status_code in (200, 201), r.text
    cliente.post("/auth/logout")
    r = cliente.post(
        "/auth/login", json={"username": "socio", "password": "contrasena-del-socio"}
    )
    assert r.status_code == 200, r.text

    resp = cliente.post("/api/empleados", json={**PEDIDO, "slugs": slugs})

    # El socio ve los numeros de sus sucursales; escribirles usuarios es otra
    # cosa. Si algun dia se abre, se abre con ese motivo y no de pasada.
    assert resp.status_code == 403, resp.text
    assert falso.altas == []


def test_sin_sucursales_el_pedido_no_es_en_todas(con_dos):
    cliente, falso, slugs = con_dos({
        "http://uno:8000": creado(), "http://dos:8000": creado(),
    })

    resp = cliente.post("/api/empleados", json={**PEDIDO, "slugs": []})

    assert resp.status_code == 422, resp.text
    assert falso.altas == []


def test_una_contrasena_corta_no_llega_a_ninguna_sede(con_dos):
    cliente, falso, slugs = con_dos({
        "http://uno:8000": creado(), "http://dos:8000": creado(),
    })

    resp = cliente.post(
        "/api/empleados", json={**PEDIDO, "password": "corta", "slugs": slugs}
    )

    assert resp.status_code == 422, resp.text
    # Importa que sea ANTES de salir: una contrasena rechazada por la segunda
    # sede dejaria al empleado creado en la primera y en ninguna otra.
    assert falso.altas == []


def test_la_contrasena_no_queda_guardada_en_el_panel(con_dos):
    """El panel no es un almacen de contrasenas.

    🔑 Se barre la base entera y no una columna: la forma en que esto se rompe
    es que alguien agregue un campo "para poder reenviarsela al empleado", y un
    assert sobre las columnas de hoy no lo vería.
    """
    cliente, falso, slugs = con_dos({
        "http://uno:8000": creado(), "http://dos:8000": creado(),
    })
    resp = cliente.post("/api/empleados", json={**PEDIDO, "slugs": slugs})
    assert resp.status_code == 200, resp.text
    assert CONTRASENA in resp.request.content.decode(), "el pedido no llevaba la contrasena"

    con_texto = []
    with db.get_engine().begin() as conexion:
        columnas = conexion.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type IN "
            "('character varying', 'text', 'character')"
        )).all()
        assert columnas, "no se leyo ninguna columna de texto: el barrido no barrio nada"
        for tabla, columna in columnas:
            cuantas = conexion.execute(
                text(f'SELECT count(*) FROM "{tabla}" WHERE "{columna}" = :v'),
                {"v": CONTRASENA},
            ).scalar_one()
            if cuantas:
                con_texto.append(f"{tabla}.{columna}")

    assert con_texto == [], f"la contrasena quedo guardada en {con_texto}"
