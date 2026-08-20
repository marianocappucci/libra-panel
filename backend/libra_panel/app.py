"""Factory del panel del dueño multisucursal.

**No es un backoffice de superadmin y no es una feature de
[[libra-backoffice]].** Comparten el patron —hablarle a N instancias por HTTP,
sin abrir ninguna base— y no el publico: alla entramos nosotros a administrar
las instancias de todos los clientes, aca entra un cliente a mirar sus propios
numeros. Mezclarlos no seria una cuestion de permisos: seria el objeto
equivocado.

**Es transversal.** No hay una rama por producto: una sucursal es una URL con
una credencial, y lo que contesta —el nucleo de LibraCore siempre, mas los
bloques de LibraCommerce o LibraGenda si los tiene— define solo lo que se
puede mostrar de ella.

Ver `wiki/analyses/panel-del-dueno-multisucursal.md`.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from libraauth.auth_events import AuthEventRepository
from libraauth.bootstrap import ensure_default_admin
from libraauth.models import Base as AuthBase
from libraauth.password_reset import PasswordResetService
from libraauth.repository import UserRepository
from libraauth.session_auth import SessionAuth, build_json_api_auth_router
from libraauth.smtp_settings import SmtpSettingsRepository, resolver_smtp_config
from libracore.security_headers import SecurityHeadersMiddleware

from . import db
from .cliente_sucursal import ClienteSucursal
# El import de `models` no es decorativo: es lo que registra `sucursales` y
# `usuario_sucursales` en el metadata de libraauth para que el `create_all` de
# abajo las cree. Sin el, las tablas no existen y no falla nada al arrancar.
from .models import ROLES
from .repositorio import RegistroDeSucursales
from .routers import resumen, sucursales, usuarios
from .settings import Settings, cargar_settings

# Fallback de desarrollo para el `SECRET_KEY` de la cookie. `_resolve_secret_key`
# de libraauth solo lo acepta con `ENV=development`, asi que un despliegue real
# sin secreto no levanta — que es lo que se quiere.
_DEV_SECRET = "libra-panel-dev-secret-no-usar-en-produccion"


def create_app(
    settings: Settings | None = None,
    frontend_dist: str | None = None,
    cliente_sucursal=None,
) -> FastAPI:
    """`cliente_sucursal` se puede inyectar; en produccion se arma del settings."""
    settings = settings or cargar_settings()

    db.configure(settings.database_url)
    # **Un solo `create_all`, y crea las cinco tablas.** Las dos del panel
    # cuelgan del mismo `Base` que `usuarios` (ver el encabezado de
    # `models.py`): sin eso, la FK de `usuario_sucursales.usuario_id` no se
    # puede resolver y el arranque corta con `NoReferencedTableError`.
    #
    # El `import` de `models` es el que registra esas dos tablas en el metadata
    # de libraauth, asi que sacarlo las haria desaparecer del `create_all` sin
    # ningun error a la vista.
    AuthBase.metadata.create_all(db.get_engine())
    sessions = db.get_session_factory()

    users = UserRepository(sessions, roles=ROLES)
    # Fail-closed: sin `LIBRA_PANEL_ADMIN_PASSWORD` la app no levanta (salvo
    # `ENV=development`). Es la variante correcta para un producto nuevo: la
    # otra (`ensure_admin_user`) genera una contrasena aleatoria y la imprime
    # en los logs del contenedor.
    ensure_default_admin(users, env_prefix="LIBRA_PANEL")

    app = FastAPI(title=f"{settings.panel_name} — Panel", docs_url=None, redoc_url=None)
    app.add_middleware(SecurityHeadersMiddleware)

    app.state.settings = settings
    app.state.users = users
    app.state.session_auth = SessionAuth(
        dev_secret_fallback=_DEV_SECRET,
        get_user_by_username=users.get_by_username,
        check_credentials=users.check_credentials,
        cookie_name="libra_panel_session",
    )
    # 🔴 **Sin esto no se registra ningun acceso Y el rate limiting del login
    # queda apagado.** Las dos cosas son opt-in por ausencia en libraauth:
    # `registrar_seguro` y `contar_fallidos_seguro` miran
    # `app.state.auth_events` y, si no esta, se van sin hacer nada y devuelven
    # 0 — o sea que el login acepta intentos ilimitados sin que nada falle a la
    # vista.
    #
    # No es un detalle de este producto: la auditoria de accesos es una de las
    # dos razones por las que el panel usa `SessionAuth` en vez de `AdminAuth`
    # (la otra es que el cliente pueda cambiar su clave sin un redeploy). Sin
    # cablearla, esa mitad de la decision no se cumple.
    app.state.auth_events = AuthEventRepository(sessions)
    app.state.registro = RegistroDeSucursales(sessions)
    app.state.cliente_sucursal = cliente_sucursal or ClienteSucursal(
        timeout=settings.timeout_sucursal
    )
    app.state.smtp_settings = SmtpSettingsRepository(sessions)
    # Recupero por correo. Sin SMTP configurado la app **levanta igual**: el
    # que avisa es el endpoint, con un 503, recien cuando alguien pide un
    # reset. `smtp_config` es un callable y no un valor para que guardar el
    # SMTP por pantalla tenga efecto sin recrear el contenedor.
    app.state.password_reset = PasswordResetService(
        sessions,
        product_name=settings.panel_name,
        reset_url_base=settings.reset_url_base,
        smtp_config=lambda: resolver_smtp_config(sessions),
    )

    @app.get("/health", include_in_schema=False)
    def health():
        """Sin auth: la usan el healthcheck de Docker y el proxy."""
        return {"ok": True, "panel": settings.panel_name}

    # 🔴 `prefix="/auth"`, el default de libraauth, y NO `/api/auth`.
    #
    # El componente `CambiarPassword` que monta el Layout de [[libra-ui]] pega
    # contra `/auth/change-password` **hardcodeado**, sin prop para cambiarlo.
    # Bajo `/api/auth` esa ruta no existiria, y como esta app sirve la SPA con
    # fallback el `POST` recibiria **200 con el index.html** en vez de un 404:
    # el boton de cambiar la contraseña fallaria sin decir por que. Es el mismo
    # modo de fallo que hace que `cliente_sucursal` valide la forma del cuerpo.
    #
    # Ademas es el prefijo que ya usan cuatro de los seis productos, asi que
    # converge hacia la convencion que alguien cumple en vez de inventar una.
    app.include_router(
        build_json_api_auth_router(prefix="/auth", incluir_password_reset=True)
    )
    app.include_router(resumen.router)
    app.include_router(sucursales.router)
    app.include_router(sucursales.mis_router)
    app.include_router(usuarios.router)

    _montar_frontend(app, frontend_dist)
    return app


def _montar_frontend(app: FastAPI, frontend_dist: str | None) -> None:
    """Sirve la SPA construida, con fallback a `index.html`.

    El fallback es lo que hace que recargar el navegador en una ruta interna no
    de 404: el ruteo lo resuelve React y el servidor devuelve siempre el mismo
    HTML.

    > ⚠️ Y es tambien la razon por la que `cliente_sucursal` valida la forma del
    > cuerpo y no se conforma con el 200: en los productos de esta familia, este
    > mismo fallback hace que *cualquier* ruta inexistente conteste 200 con
    > HTML.
    """
    dist = Path(frontend_dist or os.environ.get("FRONTEND_DIST", "/opt/frontend-dist"))
    index = dist / "index.html"
    if not index.exists():
        # En desarrollo el frontend lo sirve Vite en otro puerto. Levantar sin
        # estaticos es legitimo; fallar aca romperia la suite de tests.
        return

    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        archivo = dist / ruta
        if ruta and archivo.is_file():
            return FileResponse(archivo)
        # 🔴 `index.html` **con `Cache-Control: no-cache`**. Sin esto el
        # navegador se queda con el HTML viejo, que referencia el bundle viejo
        # por su hash — y ese bundle sigue existiendo y sigue devolviendo 200.
        # El deploy queda correcto e invisible: la version nueva esta servida y
        # nadie la ve. Los archivos de `/assets` si se cachean fuerte, porque
        # llevan el hash en el nombre.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
