"""`GET /api/salud`: cuáles de mis sucursales contestan, y cuánto tardan.

Es el análogo del `/api/salud` de libra-backoffice, con una diferencia que no es
de detalle: **el backoffice lista las instancias de todo un producto, y el panel
sólo las del usuario** (`usuario_sucursales`, para todos los roles, igual que
`/api/resumen`). Un cliente no puede enterarse de qué instancias tienen otros.

La pregunta que contesta es la que hoy sólo se puede responder mirando el
resumen o probando una sucursal por una: *¿está viva?* Va aparte del resumen a
propósito: el `/health` no hace ninguna cuenta, así que contesta en milisegundos
y permite mostrar el estado sin esperar a que las N sucursales armen sus
agregados.

**Las N consultas salen en paralelo y cada una con su propio tope** (`timeout_salud`,
más corto que el del resumen), así que una sucursal colgada demora la respuesta
lo que dura el timeout y no más. Mismo patrón que `resumen.py`: `consultar_salud`
**nunca levanta**, para poder lanzar las N con `gather` sin que una caída cancele
a las otras.

**Lo que NO dice, a propósito:** que la credencial de panel de la sucursal
funcione. El `/health` es público; probar la credencial es `POST
/api/sucursales/{slug}/probar` (admin). Para que un verde no mienta, cada fila
trae `tiene_credencial`: una sucursal que responde pero no tiene credencial
cargada va a figurar «sin respuesta» en el resumen.

Nada se cachea, por la misma razón que en el resumen: un «caída» cacheado se
queda pegado después de que la sucursal volvió.
"""
import asyncio
import time

from fastapi import APIRouter, Depends, Request, Response

from ..cliente_sucursal import SucursalSinRespuesta
from ..deps import usuario_actual

router = APIRouter(prefix="/api", tags=["salud"])


async def consultar_salud(cliente, s: dict) -> dict:
    """El estado de una sucursal. **Nunca levanta excepción.**"""
    fila = {
        "slug": s["slug"],
        "nombre": s["nombre"],
        "tiene_credencial": s["tiene_credencial"],
        "estado": "ok",
        "latencia_ms": None,
        "version": None,
        "detalle": "",
    }
    inicio = time.perf_counter()
    try:
        datos = await cliente.salud(url_base=s["url_base"])
    except SucursalSinRespuesta as exc:
        fila.update(estado="sin_respuesta", detalle=exc.detalle)
    except Exception as exc:  # noqa: BLE001 - ver el docstring
        # Red de seguridad: lo inesperado degrada ESA fila, no la pantalla.
        fila.update(
            estado="sin_respuesta", detalle=f"Error inesperado: {type(exc).__name__}: {exc}"
        )
    else:
        fila["version"] = datos.get("version")
    # La latencia se mide también cuando falla: un timeout muestra cuánto se
    # esperó, que es lo que distingue «lenta» de «apagada» al leer la fila.
    fila["latencia_ms"] = round((time.perf_counter() - inicio) * 1000)
    return fila


@router.get("/salud")
async def salud(
    request: Request,
    response: Response,
    usuario: dict = Depends(usuario_actual),
):
    registro = request.app.state.registro
    cliente = request.app.state.cliente_sucursal

    # `listar_de_usuario` y no `para_consultar`: acá no hace falta descifrar
    # ninguna credencial, y no hay por qué tenerla en memoria para esto.
    sucursales = registro.listar_de_usuario(usuario["id"], solo_activas=True)
    filas = list(await asyncio.gather(*(consultar_salud(cliente, s) for s in sucursales)))

    # `no-store`, igual que el resumen: ver el encabezado del módulo.
    response.headers["Cache-Control"] = "no-store"
    return {
        "total": len(filas),
        "respondieron": sum(1 for f in filas if f["estado"] == "ok"),
        "sucursales": filas,
    }
