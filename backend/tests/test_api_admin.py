"""Las puertas: quien entra a que, y el login propio del cliente.

El panel tiene **dos publicos en la misma aplicacion**: nosotros, que damos de
alta sucursales y cargamos credenciales, y el cliente, que mira. Lo que se
prueba aca es que la segunda mitad no pueda hacer la primera.
"""
import pytest

from .conftest import hacer_cliente

CLAVE_ADMIN = "admin-de-test"


@pytest.fixture
def socio(admin, app):
    """Un cliente logueado como `socio`, sin sucursales asignadas."""
    resp = admin.post("/api/usuarios", json={
        "username": "dueno", "name": "El dueño", "password": "clave-del-dueno", "role": "socio",
    })
    assert resp.status_code == 201, resp.text
    cliente = hacer_cliente(app)
    assert cliente.post(
        "/auth/login", json={"username": "dueno", "password": "clave-del-dueno"}
    ).status_code == 200
    return cliente


# ── El health y el login ────────────────────────────────────────────────────


def test_el_health_no_pide_sesion(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_el_admin_inicial_se_crea_solo_y_entra(client):
    resp = client.post("/auth/login", json={"username": "admin", "password": CLAVE_ADMIN})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_la_clave_equivocada_no_entra(client):
    assert client.post(
        "/auth/login", json={"username": "admin", "password": "no"}
    ).status_code == 401


def test_el_cliente_puede_cambiar_su_propia_contrasena_sin_redeploy(socio):
    """🔑 Es la razon por la que el panel usa `SessionAuth` y no `AdminAuth`.

    Con `AdminAuth` las credenciales salen del entorno: que el cliente cambie
    su propia clave requeriria que nosotros redesplegaramos su contenedor.
    """
    resp = socio.post("/auth/change-password", json={
        "current_password": "clave-del-dueno", "new_password": "clave-nueva-1",
    })
    assert resp.status_code == 200, resp.text
    socio.post("/auth/logout")
    assert socio.post(
        "/auth/login", json={"username": "dueno", "password": "clave-nueva-1"}
    ).status_code == 200


def test_el_login_queda_registrado_en_auth_log(client):
    """La otra razon del `SessionAuth`: un panel que muestra la plata de un
    negocio quiere registro de accesos."""
    from sqlalchemy import text

    from libra_panel import db

    client.post("/auth/login", json={"username": "admin", "password": CLAVE_ADMIN})
    with db.get_engine().begin() as conn:
        eventos = conn.execute(
            text("SELECT evento, username FROM auth_log ORDER BY id")
        ).fetchall()
    assert ("login", "admin") in [(e[0], e[1]) for e in eventos]


def test_el_rate_limiting_del_login_esta_encendido(client):
    """🔴 Sale del MISMO cableado que la auditoria, y por eso se prueba junto.

    `contar_fallidos_seguro` mira `app.state.auth_events` y devuelve 0 si no
    esta: sin cablearlo, el login acepta intentos ilimitados y nada falla a la
    vista. Este test es lo que distingue "esta apagado" de "esta encendido",
    porque las dos versiones contestan 401 a una clave mala.
    """
    for _ in range(5):
        assert client.post(
            "/auth/login", json={"username": "admin", "password": "mal"}
        ).status_code == 401
    resp = client.post("/auth/login", json={"username": "admin", "password": "mal"})
    assert resp.status_code == 429, resp.text


def test_el_rate_limiting_no_bloquea_al_primer_intento(client):
    """Control del anterior: una guarda que salta en uso normal es un defecto."""
    assert client.post(
        "/auth/login", json={"username": "admin", "password": CLAVE_ADMIN}
    ).status_code == 200


# ── El socio no administra ──────────────────────────────────────────────────


@pytest.mark.parametrize("metodo,ruta", [
    ("get", "/api/sucursales"),
    ("post", "/api/sucursales"),
    ("put", "/api/sucursales/x"),
    ("delete", "/api/sucursales/x"),
    ("put", "/api/sucursales/x/usuarios"),
    ("post", "/api/sucursales/x/probar"),
    ("get", "/api/usuarios"),
    ("post", "/api/usuarios"),
])
def test_el_socio_no_toca_el_registro_ni_los_usuarios(socio, metodo, ruta):
    llamar = getattr(socio, metodo)
    resp = llamar(ruta) if metodo in ("get", "delete") else llamar(ruta, json={})
    assert resp.status_code == 403, f"{metodo.upper()} {ruta} devolvio {resp.status_code}"


def test_el_socio_si_ve_lo_suyo(socio):
    assert socio.get("/api/mis-sucursales").status_code == 200
    assert socio.get("/api/resumen").status_code == 200


@pytest.mark.parametrize("ruta", ["/api/sucursales", "/api/usuarios", "/api/mis-sucursales", "/api/resumen"])
def test_sin_sesion_no_se_entra_a_nada(client, ruta):
    assert client.get(ruta).status_code == 401


# ── ABM de sucursales ───────────────────────────────────────────────────────


def alta(admin, slug="c1", **kw):
    datos = {
        "slug": slug, "nombre": slug.title(), "url_base": f"http://{slug}:8000",
        "cuit": "30-71234567-9", "razon_social": "Padel SA", "credencial": "secreta",
    }
    datos.update(kw)
    return admin.post("/api/sucursales", json=datos)


def test_el_alta_devuelve_la_sucursal_sin_la_credencial(admin):
    resp = alta(admin)
    assert resp.status_code == 201
    assert "secreta" not in resp.text
    assert resp.json()["tiene_credencial"] is True


def test_el_listado_dice_quien_ve_cada_sucursal(admin):
    alta(admin)
    uid = int(admin.get("/auth/me").json()["id"])
    admin.put("/api/sucursales/c1/usuarios", json={"usuario_ids": [uid]})

    [fila] = admin.get("/api/sucursales").json()
    assert fila["usuario_ids"] == [uid]
    assert "secreta" not in str(fila)


def test_un_slug_repetido_da_409(admin):
    alta(admin)
    assert alta(admin).status_code == 409


def test_asignar_a_un_usuario_que_no_existe_se_rechaza_entero(admin):
    """Una asignacion a medias es peor que ninguna: parece aplicada."""
    alta(admin)
    uid = int(admin.get("/auth/me").json()["id"])
    resp = admin.put("/api/sucursales/c1/usuarios", json={"usuario_ids": [uid, 99999]})
    assert resp.status_code == 409
    assert "99999" in resp.json()["detail"]
    assert admin.get("/api/sucursales").json()[0]["usuario_ids"] == []


def test_editar_una_sucursal_inexistente_da_404(admin):
    assert admin.put("/api/sucursales/fantasma", json={"nombre": "x"}).status_code == 404


def test_borrar_una_sucursal(admin):
    alta(admin)
    assert admin.delete("/api/sucursales/c1").status_code == 204
    assert admin.get("/api/sucursales").json() == []


# ── Probar una sucursal desde el alta ───────────────────────────────────────


def test_probar_avisa_cuando_la_sucursal_no_contesta(crear_app):
    from libra_panel.cliente_sucursal import SucursalSinRespuesta

    class Caido:
        async def resumen(self, **kw):
            raise SucursalSinRespuesta("HTTP 401: not authenticated")

    cliente = hacer_cliente(crear_app(cliente_sucursal=Caido()))
    cliente.post("/auth/login", json={"username": "admin", "password": CLAVE_ADMIN})
    alta(cliente)

    resp = cliente.post("/api/sucursales/c1/probar")
    assert resp.status_code == 200
    assert resp.json() == {"slug": "c1", "ok": False, "detalle": "HTTP 401: not authenticated"}


def test_probar_dice_que_bloques_contesta_esa_sucursal(crear_app):
    """El dato que evita leer un bloque ausente como un bloque en cero mas
    tarde: se ve en el alta y no cuando el dueño mira la pantalla."""

    class Contesta:
        async def resumen(self, **kw):
            return {
                "instancia": {"nombre": "Complejo Uno", "cuit": "30-71234567-9", "punto_venta": 1},
                "periodo": {"desde": "2026-08-01", "hasta": "2026-08-20"},
                "nucleo": {"facturado": 1.0},
                "comercio": {"ventas": {"cantidad": 1, "monto": 1.0}},
            }

    cliente = hacer_cliente(crear_app(cliente_sucursal=Contesta()))
    cliente.post("/auth/login", json={"username": "admin", "password": CLAVE_ADMIN})
    alta(cliente)

    datos = cliente.post("/api/sucursales/c1/probar").json()
    assert datos["ok"] is True
    assert datos["bloques"] == ["comercio", "nucleo"]
    assert datos["identidad"]["cuit"] == "30-71234567-9"


def test_probar_una_sucursal_que_no_existe_da_404(admin):
    assert admin.post("/api/sucursales/fantasma/probar").status_code == 404


# ── ABM de usuarios ─────────────────────────────────────────────────────────


def test_crear_y_listar_usuarios(admin):
    resp = admin.post("/api/usuarios", json={
        "username": "dueno", "name": "El dueño", "password": "clave-del-dueno", "role": "socio",
    })
    assert resp.status_code == 201
    assert "clave-del-dueno" not in resp.text
    assert {u["username"] for u in admin.get("/api/usuarios").json()} == {"admin", "dueno"}


def test_un_rol_que_no_existe_no_entra(admin):
    resp = admin.post("/api/usuarios", json={
        "username": "x", "name": "X", "password": "clave-larga", "role": "staff",
    })
    assert resp.status_code == 422
    assert "socio" in resp.json()["detail"]


def test_un_username_repetido_da_409(admin):
    datos = {"username": "dueno", "name": "D", "password": "clave-larga", "role": "socio"}
    assert admin.post("/api/usuarios", json=datos).status_code == 201
    assert admin.post("/api/usuarios", json=datos).status_code == 409


def test_una_contrasena_corta_no_entra(admin):
    resp = admin.post("/api/usuarios", json={
        "username": "x", "name": "X", "password": "12345", "role": "socio",
    })
    assert resp.status_code == 422


def test_el_admin_no_puede_dejarse_afuera(admin):
    """Con un solo admin, desactivarse deja el panel sin nadie que pueda dar de
    alta nada, y la unica salida es entrar a la base a mano."""
    uid = admin.get("/auth/me").json()["id"]
    resp = admin.put(f"/api/usuarios/{uid}", json={
        "name": "Admin", "role": "admin", "active": False,
    })
    assert resp.status_code == 409
    resp = admin.put(f"/api/usuarios/{uid}", json={
        "name": "Admin", "role": "socio", "active": True,
    })
    assert resp.status_code == 409


def test_el_admin_si_puede_editarse_el_nombre(admin):
    """Control del anterior: la guarda no puede bloquear el uso normal."""
    uid = admin.get("/auth/me").json()["id"]
    resp = admin.put(f"/api/usuarios/{uid}", json={
        "name": "Mariano", "role": "admin", "active": True,
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "Mariano"


def test_el_admin_le_puede_fijar_la_contrasena_a_otro(admin, app):
    creado = admin.post("/api/usuarios", json={
        "username": "dueno", "name": "D", "password": "clave-vieja", "role": "socio",
    }).json()
    assert admin.put(
        f"/api/usuarios/{creado['id']}/password", json={"password": "clave-nueva"}
    ).status_code == 200

    otro = hacer_cliente(app)
    assert otro.post(
        "/auth/login", json={"username": "dueno", "password": "clave-nueva"}
    ).status_code == 200


def test_tocar_un_usuario_que_no_existe_da_404(admin):
    assert admin.put("/api/usuarios/99999", json={
        "name": "X", "role": "socio", "active": True,
    }).status_code == 404
    assert admin.put("/api/usuarios/99999/password", json={"password": "clave-larga"}).status_code == 404


# -- La participacion del socio ---------------------------------------------
#
# Es un DATO, no un calculo: el socio ve los numeros completos de las sucursales
# donde participa, y el porcentaje se muestra al lado. Decidido el 2026-08-29.


def _alta(admin, slug="c1"):
    r = admin.post("/api/sucursales", json={
        "slug": slug, "nombre": slug.title(), "url_base": f"http://{slug}:8000",
        "cuit": "30-71234567-9", "razon_social": "Padel SA", "credencial": "secreta",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _socio(admin, nombre="dueno2"):
    r = admin.post("/api/usuarios", json={
        "username": nombre, "name": nombre.title(),
        "password": f"clave-{nombre}", "role": "socio",
    })
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def test_se_carga_la_participacion_y_viaja_con_el_listado(admin):
    """La pantalla la muestra en la misma fila que la asignacion, asi que tiene
    que venir con el listado y no en una llamada por sucursal."""
    _alta(admin)
    uid = _socio(admin)
    assert admin.put("/api/sucursales/c1/usuarios", json={"usuario_ids": [uid]}).status_code == 200

    r = admin.put("/api/sucursales/c1/participacion",
                  json={"usuario_id": uid, "participacion": "33.33"})
    assert r.status_code == 200, r.text
    assert r.json()["participacion"] == 33.33

    fila = next(s for s in admin.get("/api/sucursales").json() if s["slug"] == "c1")
    assert fila["participaciones"] == {str(uid): 33.33}


def test_un_porcentaje_fuera_de_rango_lo_rechaza_el_esquema(admin):
    _alta(admin)
    uid = _socio(admin)
    admin.put("/api/sucursales/c1/usuarios", json={"usuario_ids": [uid]})
    for malo in (101, -1):
        r = admin.put("/api/sucursales/c1/participacion",
                      json={"usuario_id": uid, "participacion": malo})
        assert r.status_code == 422, f"{malo} entro: {r.text}"
    # El control: uno valido si entra.
    assert admin.put("/api/sucursales/c1/participacion",
                     json={"usuario_id": uid, "participacion": 50}).status_code == 200


def test_a_quien_no_tiene_la_sucursal_asignada_da_409_y_no_404(admin):
    """La sucursal existe y el usuario tambien; lo que falta es la asignacion.
    Un 404 mandaria a mirar si el slug esta bien escrito."""
    _alta(admin)
    uid = _socio(admin)
    r = admin.put("/api/sucursales/c1/participacion",
                  json={"usuario_id": uid, "participacion": 50})
    assert r.status_code == 409, r.text
    # El control: asignandolo primero, entra.
    admin.put("/api/sucursales/c1/usuarios", json={"usuario_ids": [uid]})
    assert admin.put("/api/sucursales/c1/participacion",
                     json={"usuario_id": uid, "participacion": 50}).status_code == 200


def test_sobre_una_sucursal_que_no_existe_da_404(admin):
    uid = _socio(admin)
    assert admin.put("/api/sucursales/no-existe/participacion",
                     json={"usuario_id": uid, "participacion": 50}).status_code == 404


def test_UN_SOCIO_NO_PUEDE_CARGAR_PARTICIPACIONES(socio):
    """🔴 Es el ABM del registro: lo administra el admin del panel.

    Un socio que pudiera escribir su propio porcentaje estaria editando el
    registro que dice quien ve que.
    """
    r = socio.put("/api/sucursales/c1/participacion",
                  json={"usuario_id": 1, "participacion": 50})
    assert r.status_code == 403, r.text


def test_EL_SOCIO_SIGUE_VIENDO_LOS_NUMEROS_COMPLETOS(crear_app):
    """🔴 La lectura elegida: participacion como FILTRO, no como proporcion.

    Se compara el resumen que ve el socio con 100% y con 1%: tiene que ser el
    MISMO numero. Si algun dia difiere, alguien implemento la otra lectura ---la
    de "su parte"--- sin volver a decidirla.

    Se pega en `/api/resumen`, que es donde el socio ve la plata, con el cliente
    doble que usa `test_resumen.py`: lo que se mide es lo que llega a la
    pantalla, no lo que devuelve el repositorio.
    """
    from .conftest import hacer_cliente
    from .test_resumen import NUCLEO, ClienteFalso

    doble = ClienteFalso({"http://c1:8000": {"nucleo": dict(NUCLEO)}})
    app = crear_app(cliente_sucursal=doble)

    admin = hacer_cliente(app)
    import os
    assert admin.post("/auth/login", json={
        "username": "admin", "password": os.environ["LIBRA_PANEL_ADMIN_PASSWORD"],
    }).status_code == 200

    _alta(admin)
    uid = _socio(admin, "duenoc")
    admin.put("/api/sucursales/c1/usuarios", json={"usuario_ids": [uid]})

    cliente = hacer_cliente(app)
    assert cliente.post(
        "/auth/login", json={"username": "duenoc", "password": "clave-duenoc"}
    ).status_code == 200

    admin.put("/api/sucursales/c1/participacion",
              json={"usuario_id": uid, "participacion": 100})
    con_100 = cliente.get("/api/resumen").json()
    admin.put("/api/sucursales/c1/participacion",
              json={"usuario_id": uid, "participacion": 1})
    con_1 = cliente.get("/api/resumen").json()

    # Control de que el test mide algo: el resumen trae plata, no viene vacio.
    assert con_100["consolidado"]["nucleo"]["datos"]["facturado"] == 100.0, con_100
    assert con_100 == con_1, (
        "la participacion esta cambiando lo que ve el socio: eso es la otra lectura"
    )
