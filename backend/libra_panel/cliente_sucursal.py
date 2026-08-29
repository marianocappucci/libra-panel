"""El cliente HTTP con el que el panel le pregunta los numeros a una sucursal.

**El panel no abre la base de ninguna sucursal.** Le pide a cada una que haga
la cuenta en su propio proceso y le conteste agregados. Eso es lo que hace que
no necesite credenciales de ninguna base, ni convivir con N `SECRET_KEY` en un
solo entorno.

La autenticacion es la credencial de panel de [[libraauth]] v0.29.0
(`X-Panel-Auth`), **una por sucursal**, guardada cifrada en el registro. No es
el `LIBRA_SERVICE_TOKEN` del producto: ese es uno solo para todas las
instancias del mismo producto, asi que dárselo a un cliente le abriria las de
los demas.

Ver `wiki/analyses/panel-del-dueno-multisucursal.md`, punto 7.
"""
import httpx

#: Header que mira `libraauth.session_auth.token_de_panel_valido`.
HEADER_CREDENCIAL = "X-Panel-Auth"

#: Ruta que expone la factory `libracore.resumen_router.build_resumen_router`.
RUTA_RESUMEN = "/api/resumen"


class EmpleadoYaExiste(Exception):
    """Esa sucursal ya tiene un usuario con ese nombre.

    🔑 **No es un error del aprovisionamiento: es el caso normal.** Un empleado
    que ya trabajaba en una sede y ahora suma otra viene a esto en la primera y
    a un alta en la segunda. La pantalla lo muestra como "ya estaba", no como
    una falla, y el resto de las sucursales sigue.
    """


class SucursalSinRespuesta(Exception):
    """La sucursal no contesto, o contesto algo que no sirve.

    **No es un error del panel y no es un cero.** El router lo convierte en una
    fila "sin respuesta" con el detalle adentro, y el total queda marcado como
    parcial. Confundir esto con "vendio cero" es el modo de fallo que este
    producto existe para no tener.
    """

    def __init__(self, detalle: str):
        self.detalle = detalle
        super().__init__(detalle)


class ClienteSucursal:
    def __init__(self, *, timeout: float, transport=None):
        self._timeout = timeout
        # Costura para los tests: con un `ASGITransport` la suite le habla a
        # una app FastAPI de verdad —con el router real de la factory de
        # LibraCore y su guard real— en vez de a un doble que podria estar de
        # acuerdo con un contrato equivocado. En produccion es siempre `None`.
        self._transport = transport

    async def resumen(self, *, url_base: str, credencial: str, desde: str, hasta: str) -> dict:
        """El resumen de una sucursal, o `SucursalSinRespuesta`.

        Devuelve el cuerpo tal cual lo manda la sucursal: `instancia`,
        `periodo`, `nucleo` y los bloques que ese producto pueda contestar. El
        panel **no completa los bloques que faltan**: un bloque ausente no es
        un bloque en cero, y esa distincion tiene que sobrevivir hasta la
        pantalla.
        """
        if not credencial:
            # Se corta antes de salir a la red: sin credencial la sucursal
            # contestaria 401 y la fila diria "no autenticado", que suena a
            # credencial equivocada. Lo cierto es que el alta quedo a medias.
            raise SucursalSinRespuesta(
                "Esta sucursal no tiene credencial cargada en el panel."
            )

        url = f"{url_base.rstrip('/')}{RUTA_RESUMEN}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as cliente:
                resp = await cliente.get(
                    url,
                    params={"desde": desde, "hasta": hasta},
                    headers={HEADER_CREDENCIAL: credencial},
                )
        except httpx.HTTPError as exc:
            # Timeout, DNS que no resuelve, conexion rechazada. Es "esa
            # sucursal esta caida", que es informacion y no una falla del panel.
            raise SucursalSinRespuesta(f"{type(exc).__name__}: {exc}") from exc

        if resp.status_code >= 400:
            raise SucursalSinRespuesta(_detalle_de_error(resp))

        return _cuerpo_valido(resp)


    async def crear_usuario(
        self, *, url_base: str, credencial: str, ruta: str, datos: dict
    ) -> dict:
        """Da de alta un empleado en esa sucursal. Devuelve el usuario creado.

        🔴 **Entra con la credencial del panel, que es POR INSTANCIA.** No con
        el `LIBRA_SERVICE_TOKEN`, que es uno por producto y lo comparten todas
        sus instancias: darselo al panel habria hecho que un panel comprometido
        abriera la escritura en todas. Del otro lado lo acepta
        `json_api_require_admin_o_servicio_o_panel` (libraauth v0.35.0), que los
        productos declaran **solo** en su router de usuarios.

        ⚠️ **`ruta` viene de la sucursal y no es una constante.** El router de
        usuarios no es de libraauth ---cada producto tiene el suyo--- y esta en
        `/api/usuarios` en cinco productos y en `/users` en tres. Ver el
        comentario de `Sucursal.ruta_de_usuarios`.

        Un 409 sale como `EmpleadoYaExiste` y no como falla: es el caso normal
        de un empleado que ya trabajaba en esa sede.
        """
        if not credencial:
            raise SucursalSinRespuesta(
                "Esta sucursal no tiene credencial cargada en el panel."
            )

        url = f"{url_base.rstrip('/')}/{ruta.strip('/')}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as cliente:
                resp = await cliente.post(
                    url, json=datos, headers={HEADER_CREDENCIAL: credencial},
                )
        except httpx.HTTPError as exc:
            raise SucursalSinRespuesta(f"{type(exc).__name__}: {exc}") from exc

        if resp.status_code == 409:
            raise EmpleadoYaExiste(_detalle_de_error(resp))
        if resp.status_code >= 400:
            raise SucursalSinRespuesta(_detalle_de_error(resp))
        return _usuario_valido(resp)


def _usuario_valido(resp: httpx.Response) -> dict:
    """Valida la forma antes de creerle al 2xx, igual que `_cuerpo_valido`.

    ⚠️ **NO defiende del fallback de la SPA, aunque lo parezca.** Medido el
    2026-08-29 en los ocho productos: los ocho montan su catch-all como
    `@app.get`, asi que un `POST` a una ruta que no existe da 405 o 404 y nunca
    200 con el `index.html`. El caso que en el resumen ---que va por `GET`---
    hace falta cubrir, aca no se puede producir. Escribir el codigo suponiendo
    que si, y despues un test que lo "demuestre" con un doble armado a mano,
    habria sido probar mi propia suposicion.

    🔑 **Lo que si hace es exigir el contrato del 2xx.** El alta es una
    escritura y su modo de fallar es mudo: si una sede contesta 200 con
    cualquier otra cosa, el panel diria "empleado creado" y el dueño se entera
    el dia que el empleado no puede entrar. Un `url_base` apuntado a otro
    contenedor de la red de control, o un producto que cambie la forma de la
    respuesta, entran por aca.
    """
    try:
        cuerpo = resp.json()
    except ValueError:
        raise SucursalSinRespuesta(
            "Contesto sin JSON. Suele ser el fallback de la SPA: esa sucursal "
            "no expone su router de usuarios en la ruta cargada."
        ) from None
    if not isinstance(cuerpo, dict) or "username" not in cuerpo:
        raise SucursalSinRespuesta(
            "Contesto un cuerpo que no es un usuario. Revisar la ruta de "
            "usuarios de esta sucursal."
        )
    return cuerpo


def _cuerpo_valido(resp: httpx.Response) -> dict:
    """Valida la forma antes de creerle al 200.

    🔴 **Un 200 no alcanza.** Los productos de esta familia sirven una SPA con
    fallback, asi que *cualquier* ruta que no exista devuelve 200 con el
    `index.html`. Una sucursal con el motor viejo —sin el router de resumen—
    contestaria 200 con HTML, el panel lo leeria como exito y sumaria cero: el
    cero que parece un dato. Medido el 2026-08-20 contra `contalibra`: una ruta
    inventada devuelve 200 `text/html`, mientras `/api/resumen` devuelve 401
    JSON.
    """
    try:
        cuerpo = resp.json()
    except ValueError:
        raise SucursalSinRespuesta(
            "Contesto 200 pero el cuerpo no es JSON. Suele ser el fallback de "
            "la SPA: esa URL no expone /api/resumen (motor viejo, o url_base "
            "mal cargada)."
        ) from None
    if not isinstance(cuerpo, dict):
        raise SucursalSinRespuesta(
            f"Contesto 200 con un {type(cuerpo).__name__} y no con un objeto JSON."
        )
    if "nucleo" not in cuerpo:
        # El nucleo lo tienen los seis productos: sale de LibraCore, que esta
        # en todos. Que falte no es "esta sucursal no factura" — es que del
        # otro lado no hay un resumen.
        raise SucursalSinRespuesta(
            "Contesto un JSON sin la clave 'nucleo'. No es la respuesta de "
            "/api/resumen."
        )
    return cuerpo


def _detalle_de_error(resp: httpx.Response) -> str:
    try:
        cuerpo = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}"
    if isinstance(cuerpo, dict) and "detail" in cuerpo:
        return f"HTTP {resp.status_code}: {cuerpo['detail']}"
    return f"HTTP {resp.status_code}"
