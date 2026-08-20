"""El registro de sucursales: credenciales en reposo y la asignacion por usuario."""
import pytest
from sqlalchemy import text

from libra_panel import db
from libra_panel.repositorio import (
    RegistroDeSucursales, SlugTomado, SucursalDesconocida,
)


@pytest.fixture
def registro(app):
    """El registro de una app ya creada (que es la que corrio `create_all`)."""
    return app.state.registro


def crear(registro, slug="c1", **kw):
    datos = {
        "slug": slug, "nombre": slug.title(), "url_base": "http://c1:8000",
        "cuit": "30-71234567-9", "razon_social": "Padel SA", "credencial": "secreta-1",
    }
    datos.update(kw)
    return registro.crear(**datos)


# ── La credencial ───────────────────────────────────────────────────────────


def test_la_credencial_no_se_guarda_en_claro(registro):
    """Se mira la COLUMNA, no lo que devuelve el repositorio.

    Un test que solo chequeara `credencial_de()` pasaria igual con la
    credencial guardada en texto plano: lo que se quiere verificar es que un
    dump de la base no alcance para leerle los numeros a las sucursales de un
    cliente.
    """
    crear(registro, credencial="la-credencial-de-verdad")
    with db.get_engine().begin() as conn:
        guardado = conn.execute(
            text("SELECT credencial_cifrada FROM sucursales WHERE slug = 'c1'")
        ).scalar_one()

    assert "la-credencial-de-verdad" not in guardado
    # Marca de version del formato de `libraauth.crypto`.
    assert guardado.startswith("v1:")


def test_la_credencial_vuelve_descifrada_para_armar_el_header(registro):
    crear(registro, credencial="la-credencial-de-verdad")
    assert registro.credencial_de("c1") == "la-credencial-de-verdad"


def test_la_credencial_nunca_sale_en_los_diccionarios_de_la_api(registro):
    creada = crear(registro, credencial="secretisima")
    listada = registro.listar()[0]
    for salida in (creada, listada, registro.obtener("c1")):
        assert "credencial" not in salida
        assert "credencial_cifrada" not in salida
        assert "secretisima" not in str(salida)
    assert creada["tiene_credencial"] is True


def test_sin_credencial_se_distingue_de_una_credencial_vacia(registro):
    crear(registro, slug="sin", credencial="")
    assert registro.obtener("sin")["tiene_credencial"] is False
    assert registro.credencial_de("sin") == ""


def test_editar_sin_mandar_credencial_no_la_borra(registro):
    """El formulario nunca la recibe: si mandara siempre su campo, mandaria
    vacio, y editar el nombre le borraria la credencial a la sucursal."""
    crear(registro, credencial="secreta-1")
    registro.actualizar("c1", nombre="Nombre nuevo")
    assert registro.credencial_de("c1") == "secreta-1"
    assert registro.obtener("c1")["nombre"] == "Nombre nuevo"


def test_mandar_credencial_vacia_si_la_borra(registro):
    crear(registro, credencial="secreta-1")
    registro.actualizar("c1", credencial="")
    assert registro.obtener("c1")["tiene_credencial"] is False


# ── Alta y unicidad ─────────────────────────────────────────────────────────


def test_dos_sucursales_no_pueden_compartir_slug(registro):
    crear(registro)
    with pytest.raises(SlugTomado):
        crear(registro)


def test_la_url_pierde_la_barra_final(registro):
    """`http://c1:8000/` + `/api/resumen` daria una doble barra."""
    creada = crear(registro, url_base="http://c1:8000/")
    assert creada["url_base"] == "http://c1:8000"


def test_tocar_una_sucursal_que_no_existe_avisa(registro):
    with pytest.raises(SucursalDesconocida):
        registro.actualizar("fantasma", nombre="x")
    with pytest.raises(SucursalDesconocida):
        registro.eliminar("fantasma")


# ── La asignacion, que es el aislamiento ────────────────────────────────────


def test_un_usuario_solo_ve_lo_que_tiene_asignado(app, registro):
    users = app.state.users
    uno = users.create(username="uno", name="Uno", password="clave-uno", role="socio")
    dos = users.create(username="dos", name="Dos", password="clave-dos", role="socio")
    crear(registro, slug="a", url_base="http://a:8000")
    crear(registro, slug="b", url_base="http://b:8000")
    registro.asignar("a", [int(uno["id"])])
    registro.asignar("b", [int(dos["id"])])

    assert [s["slug"] for s in registro.listar_de_usuario(uno["id"])] == ["a"]
    assert [s["slug"] for s in registro.listar_de_usuario(dos["id"])] == ["b"]


def test_asignar_dos_veces_no_duplica_la_sucursal_en_el_consolidado(app, registro):
    """🔴 Una fila repetida haria entrar la sucursal DOS VECES en la suma.

    El facturado saldria al doble, con cara de numero correcto. Lo impide la
    `UNIQUE(usuario_id, sucursal_id)` de la base, no el router — y por eso este
    test corre contra PostgreSQL: SQLite con el pragma de FKs apagado la
    ignora.
    """
    uno = app.state.users.create(username="uno", name="Uno", password="clave-uno", role="socio")
    crear(registro, slug="a", url_base="http://a:8000")
    registro.asignar("a", [int(uno["id"]), int(uno["id"])])

    assert [s["slug"] for s in registro.listar_de_usuario(uno["id"])] == ["a"]
    with db.get_engine().begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM usuario_sucursales")).scalar_one() == 1


def test_la_base_rechaza_una_asignacion_duplicada_insertada_a_mano(app, registro):
    """Control del anterior: prueba la constraint, no el `set()` de Python."""
    from sqlalchemy.exc import IntegrityError

    uno = app.state.users.create(username="uno", name="Uno", password="clave-uno", role="socio")
    crear(registro, slug="a", url_base="http://a:8000")
    registro.asignar("a", [int(uno["id"])])

    with pytest.raises(IntegrityError):
        with db.get_engine().begin() as conn:
            conn.execute(text(
                "INSERT INTO usuario_sucursales (usuario_id, sucursal_id) "
                "SELECT :u, id FROM sucursales WHERE slug = 'a'"
            ), {"u": int(uno["id"])})


def test_asignar_reemplaza_el_conjunto_entero(app, registro):
    users = app.state.users
    uno = users.create(username="uno", name="Uno", password="clave-uno", role="socio")
    dos = users.create(username="dos", name="Dos", password="clave-dos", role="socio")
    crear(registro, slug="a", url_base="http://a:8000")

    registro.asignar("a", [int(uno["id"]), int(dos["id"])])
    assert registro.usuarios_de("a") == sorted([int(uno["id"]), int(dos["id"])])
    # Sacar a `dos` es mandar la lista sin el: la pantalla manda el conjunto.
    registro.asignar("a", [int(uno["id"])])
    assert registro.usuarios_de("a") == [int(uno["id"])]


def test_borrar_una_sucursal_se_lleva_sus_asignaciones(app, registro):
    """`ON DELETE CASCADE`. Sin esto quedarian filas apuntando a una sucursal
    que no existe, y el join las descartaria en silencio."""
    uno = app.state.users.create(username="uno", name="Uno", password="clave-uno", role="socio")
    crear(registro, slug="a", url_base="http://a:8000")
    registro.asignar("a", [int(uno["id"])])
    registro.eliminar("a")

    with db.get_engine().begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM usuario_sucursales")).scalar_one() == 0


def test_una_sucursal_desactivada_no_entra_en_la_consulta(app, registro):
    uno = app.state.users.create(username="uno", name="Uno", password="clave-uno", role="socio")
    crear(registro, slug="a", url_base="http://a:8000", activa=False)
    registro.asignar("a", [int(uno["id"])])

    assert registro.listar_de_usuario(uno["id"]) == []
    assert registro.para_consultar(uno["id"]) == []
    # Pero sigue en el registro, para poder reactivarla.
    assert registro.obtener("a")["activa"] is False


def test_para_consultar_trae_la_credencial_y_no_la_expone_como_dict(app, registro):
    uno = app.state.users.create(username="uno", name="Uno", password="clave-uno", role="socio")
    crear(registro, slug="a", url_base="http://a:8000", credencial="secreta-a")
    registro.asignar("a", [int(uno["id"])])

    [s] = registro.para_consultar(uno["id"])
    assert s.credencial == "secreta-a"
    assert s.problema == ""
    # No es un dict: no se puede serializar por accidente en una respuesta.
    assert not isinstance(s, dict)


def test_una_sucursal_sin_credencial_sale_con_problema_y_no_tumba_al_resto(app, registro):
    uno = app.state.users.create(username="uno", name="Uno", password="clave-uno", role="socio")
    crear(registro, slug="a", url_base="http://a:8000", credencial="secreta-a")
    crear(registro, slug="b", url_base="http://b:8000", credencial="")
    registro.asignar("a", [int(uno["id"])])
    registro.asignar("b", [int(uno["id"])])

    por_slug = {s.slug: s for s in registro.para_consultar(uno["id"])}
    assert por_slug["a"].problema == ""
    assert "no tiene credencial cargada" in por_slug["b"].problema


def test_un_usuario_sin_id_numerico_no_ve_ninguna(registro):
    """El `PANEL_USER`/`SERVICE_USER` de libraauth tiene `id: None`."""
    assert registro.listar_de_usuario(None) == []
    assert RegistroDeSucursales(db.get_session_factory()).listar_de_usuario("@panel") == []
