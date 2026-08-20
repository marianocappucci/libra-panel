"""`GET /api/resumen`: los numeros de las N sucursales del usuario, en vivo.

**Las N llamadas salen en paralelo y cada una con su propio timeout.** En serie,
cinco sucursales de las que una esta colgada convierten la pantalla en un
minuto de spinner; y sin timeout, en un spinner para siempre.

**Nada se cachea.** El pedido fue en vivo, y cachear en vivo es contradecirse.
Peor: un total parcial cacheado se queda pegado despues de que la sucursal
volvio, asi que el dueño ve el numero chico un rato mas y sin ninguna señal.

🔴 **El alcance sale SIEMPRE de `usuario_sucursales`, para todos los roles.**
No hay una rama para admin que consulte todo: sumar las sucursales de clientes
distintos daria un numero que no significa nada, y ademas le mostraria a uno
los de otro. Un admin sin asignaciones ve un panel vacio, y esta bien.
"""
import asyncio
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..cliente_sucursal import SucursalSinRespuesta
from ..consolidado import ResultadoSucursal, armar_respuesta
from ..deps import usuario_actual
from ..fechas import rango_por_defecto
from ..repositorio import SucursalParaConsultar

router = APIRouter(prefix="/api", tags=["resumen"])


def validar_periodo(desde: str, hasta: str) -> tuple[str, str]:
    """Fechas ISO y en orden, o 422. Sin nada, el mes en curso en hora de AR.

    ISO y no `dd-mm-aaaa` a proposito: es una API entre maquinas, y es
    exactamente el formato que despues se le reenvia a cada sucursal. El
    `dd-mm-aaaa` del estandar de la familia es de presentacion y lo pone la
    pantalla.
    """
    por_defecto = rango_por_defecto()
    desde_ = desde or por_defecto[0]
    hasta_ = hasta or por_defecto[1]
    for etiqueta, valor in (("desde", desde_), ("hasta", hasta_)):
        try:
            datetime.date.fromisoformat(valor)
        except ValueError:
            raise HTTPException(
                422, f"`{etiqueta}` tiene que ser una fecha ISO (aaaa-mm-dd)"
            ) from None
    if desde_ > hasta_:
        raise HTTPException(422, "`desde` no puede ser posterior a `hasta`")
    return desde_, hasta_


async def consultar_una(cliente, s: SucursalParaConsultar, desde: str, hasta: str) -> ResultadoSucursal:
    """Le pregunta a una sucursal. **Nunca levanta excepcion.**

    Es lo que permite lanzar las N con `gather` sin `return_exceptions`: cada
    una se resuelve en un resultado, contestara o no. Si esta funcion pudiera
    fallar, una sucursal caida cancelaria la consulta de las otras cuatro y la
    pantalla no mostraria nada — cuando lo correcto es mostrar cuatro y decir
    que falta una.
    """
    base = {
        "slug": s.slug, "nombre": s.nombre, "cuit": s.cuit, "razon_social": s.razon_social,
    }
    if s.problema:
        return ResultadoSucursal(**base, ok=False, detalle=s.problema)
    try:
        datos = await cliente.resumen(
            url_base=s.url_base, credencial=s.credencial, desde=desde, hasta=hasta,
        )
    except SucursalSinRespuesta as exc:
        return ResultadoSucursal(**base, ok=False, detalle=exc.detalle)
    except Exception as exc:  # noqa: BLE001 - ver el comentario
        # Red de seguridad: cualquier cosa inesperada de una sucursal degrada
        # ESA fila, no la pantalla. Un `AttributeError` en el parseo de una
        # respuesta rara no puede dejar al dueño sin ver las otras cuatro.
        return ResultadoSucursal(
            **base, ok=False, detalle=f"Error inesperado: {type(exc).__name__}: {exc}"
        )
    return ResultadoSucursal(**base, ok=True, datos=datos)


@router.get("/resumen")
async def resumen(
    request: Request,
    response: Response,
    desde: str = Query(default=""),
    hasta: str = Query(default=""),
    usuario: dict = Depends(usuario_actual),
):
    desde_, hasta_ = validar_periodo(desde, hasta)
    registro = request.app.state.registro
    cliente = request.app.state.cliente_sucursal

    sucursales = registro.para_consultar(usuario["id"])
    resultados = list(
        await asyncio.gather(
            *(consultar_una(cliente, s, desde_, hasta_) for s in sucursales)
        )
    )

    # 🔴 `no-store` y no `no-cache`: `no-cache` permite guardar y revalidar, y
    # lo que no se quiere es que exista una copia de un total parcial en ningun
    # lado. Ver el encabezado del modulo.
    response.headers["Cache-Control"] = "no-store"
    return armar_respuesta(desde=desde_, hasta=hasta_, resultados=resultados)
