"""El registro de sucursales: ABM y asignacion. **Solo admin.**

El panel es de **solo lectura hacia las sucursales**: no hay un endpoint que le
escriba nada a ninguna. Lo que se administra aca es el registro propio del
panel —que sucursal existe, en que URL, con que credencial y quien la ve—, que
es otra cosa.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..cliente_sucursal import SucursalSinRespuesta
from ..deps import requiere_admin, usuario_actual
from ..fechas import rango_por_defecto
from ..repositorio import (
    AsignacionDesconocida, ParticipacionInvalida, SlugTomado, SucursalDesconocida,
)

router = APIRouter(prefix="/api/sucursales", tags=["sucursales"])


class SucursalIn(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    nombre: str = Field(min_length=1, max_length=200)
    #: En el VPS es el nombre del contenedor en la red de control
    #: (`http://contalibra:8000`): el trafico del panel no sale a internet.
    url_base: str = Field(min_length=1, max_length=300)
    cuit: str = ""
    razon_social: str = ""
    #: La credencial de panel de esta sucursal (su `LIBRA_PANEL_TOKEN`). Entra
    #: por aca y no vuelve a salir nunca: se guarda cifrada.
    credencial: str = ""
    activa: bool = True


class SucursalPatch(BaseModel):
    """Todo opcional. **`credencial=None` deja la guardada como esta.**

    La pantalla nunca recibe la credencial, asi que si el formulario mandara
    siempre su campo mandaria vacio, y editar el nombre de una sucursal le
    borraria la credencial. Para borrarla hay que mandar `""` explicito.
    """

    nombre: str | None = None
    url_base: str | None = None
    cuit: str | None = None
    razon_social: str | None = None
    credencial: str | None = None
    activa: bool | None = None


class AsignacionIn(BaseModel):
    usuario_ids: list[int]


class ParticipacionIn(BaseModel):
    usuario_id: int
    #: 0..100. El rango lo validan el repositorio **y** la base; acá se declara
    #: para que un texto o un negativo no lleguen siquiera al servicio.
    participacion: Decimal = Field(ge=0, le=100)


@router.get("", dependencies=[Depends(requiere_admin)])
def listar(request: Request):
    registro = request.app.state.registro
    return [
        {
            **s,
            "usuario_ids": registro.usuarios_de(s["slug"]),
            # 🔑 Las participaciones viajan con el listado y no en una llamada
            # aparte: la pantalla las muestra en la misma fila que la asignación,
            # y pedirlas de a una sería una request por sucursal.
            #
            # Las claves salen como texto porque JSON no tiene enteros por clave;
            # la pantalla las vuelve a leer por el id del usuario.
            "participaciones": {
                str(uid): float(p)
                for uid, p in registro.participaciones_de(s["slug"]).items()
            },
        }
        for s in registro.listar()
    ]


@router.post("", dependencies=[Depends(requiere_admin)], status_code=201)
def crear(datos: SucursalIn, request: Request):
    try:
        return request.app.state.registro.crear(**datos.model_dump())
    except SlugTomado:
        raise HTTPException(409, f"Ya existe una sucursal con el slug {datos.slug!r}.") from None


@router.put("/{slug}", dependencies=[Depends(requiere_admin)])
def actualizar(slug: str, datos: SucursalPatch, request: Request):
    try:
        # `exclude_unset` y no `exclude_none`: es lo que distingue "no mande el
        # campo" de "lo mande vacio a proposito". Con `exclude_none`, borrar la
        # credencial mandando `""` funcionaria, pero no mandarla tambien —
        # y son cosas distintas.
        return request.app.state.registro.actualizar(
            slug, **datos.model_dump(exclude_unset=True)
        )
    except SucursalDesconocida:
        raise HTTPException(404, f"No existe la sucursal {slug!r}.") from None


@router.delete("/{slug}", dependencies=[Depends(requiere_admin)], status_code=204)
def eliminar(slug: str, request: Request):
    try:
        request.app.state.registro.eliminar(slug)
    except SucursalDesconocida:
        raise HTTPException(404, f"No existe la sucursal {slug!r}.") from None


@router.put("/{slug}/usuarios", dependencies=[Depends(requiere_admin)])
def asignar(slug: str, datos: AsignacionIn, request: Request):
    """Fija el conjunto completo de usuarios que ven esta sucursal."""
    registro = request.app.state.registro
    usuarios = request.app.state.users
    existentes = {int(u["id"]) for u in usuarios.list()}
    desconocidos = sorted(set(datos.usuario_ids) - existentes)
    if desconocidos:
        # 409 y no 404: el que no existe no es el recurso de la URL. Y se
        # rechaza la lista entera en vez de asignar los que si existen — una
        # asignacion a medias es peor que ninguna, porque parece aplicada.
        raise HTTPException(409, f"Estos usuarios no existen: {desconocidos}.")
    try:
        return {"slug": slug, "usuario_ids": registro.asignar(slug, datos.usuario_ids)}
    except SucursalDesconocida:
        raise HTTPException(404, f"No existe la sucursal {slug!r}.") from None


@router.put("/{slug}/participacion", dependencies=[Depends(requiere_admin)])
def participacion(slug: str, datos: ParticipacionIn, request: Request):
    """El porcentaje de un socio en esta sucursal.

    🔑 **Es un dato informativo: no cambia ningún número.** El socio ve la
    facturación completa de las sucursales donde participa. Decidido así el
    2026-08-29 entre las dos lecturas posibles; la otra ---que viera "su
    parte"--- arrastra decisiones que no son de software.

    Va aparte de `PUT /{slug}/usuarios` a propósito: aquél fija **quién ve**, y
    es lo que da acceso. Mezclarlos en un payload haría que cargar un porcentaje
    pudiera revocarle el acceso a otro socio por omisión.
    """
    registro = request.app.state.registro
    try:
        valor = registro.fijar_participacion(slug, datos.usuario_id, datos.participacion)
    except SucursalDesconocida:
        raise HTTPException(404, f"No existe la sucursal {slug!r}.") from None
    except AsignacionDesconocida as e:
        # 409 y no 404: la sucursal existe y el usuario tambien; lo que falta es
        # la asignacion. Un 404 mandaria a mirar si el slug esta bien escrito.
        raise HTTPException(409, str(e)) from None
    except ParticipacionInvalida as e:
        raise HTTPException(422, str(e)) from None
    return {"slug": slug, "usuario_id": datos.usuario_id, "participacion": float(valor)}


@router.post("/{slug}/probar", dependencies=[Depends(requiere_admin)])
async def probar(slug: str, request: Request):
    """Una sola llamada real, para verificar el alta sin abrir el panel.

    Existe porque el modo de fallo caro es un alta que parece completa: URL
    escrita, credencial cargada, y del otro lado un 401 que recien se descubre
    cuando el dueño mira su pantalla y ve "4 de 5". Esto lo dice en el momento.
    """
    registro = request.app.state.registro
    s = registro.obtener(slug)
    if s is None:
        raise HTTPException(404, f"No existe la sucursal {slug!r}.")
    try:
        credencial = registro.credencial_de(slug)
    except Exception as exc:  # noqa: BLE001
        return {"slug": slug, "ok": False, "detalle": f"Credencial ilegible: {exc}"}

    desde, hasta = rango_por_defecto()
    try:
        datos = await request.app.state.cliente_sucursal.resumen(
            url_base=s["url_base"], credencial=credencial, desde=desde, hasta=hasta,
        )
    except SucursalSinRespuesta as exc:
        return {"slug": slug, "ok": False, "detalle": exc.detalle}
    return {
        "slug": slug,
        "ok": True,
        "detalle": "",
        "identidad": datos.get("instancia") or {},
        # Que bloques contesta esta sucursal. Es el dato que dice si el panel
        # va a poder mostrarle comercio o solo el nucleo — y verlo en el alta
        # evita leer un bloque ausente como un bloque en cero mas tarde.
        "bloques": sorted(k for k in datos if k not in ("instancia", "periodo")),
    }


# La vista del cliente va en un router aparte, con prefijo `/api` y no
# `/api/sucursales`: una ruta fija como `/api/sucursales/mias` conviviria con
# `/api/sucursales/{slug}` y cual gana lo decidiria el orden de registro — la
# clase de detalle que se rompe cuando alguien reordena los `include_router`.
mis_router = APIRouter(prefix="/api", tags=["sucursales"])


@mis_router.get("/mis-sucursales")
def mis_sucursales(request: Request, usuario: dict = Depends(usuario_actual)):
    """El registro de lo que ve este usuario, **sin salir a la red.**

    La pantalla la usa para dibujar las filas antes de que vuelvan los numeros,
    y para saber cuantas espera: asi el "N de M" tiene un M desde el primer
    frame y no aparece recien al final.
    """
    return request.app.state.registro.listar_de_usuario(usuario["id"])
