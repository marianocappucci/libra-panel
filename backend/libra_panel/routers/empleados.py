"""El alta de un empleado en varias sucursales, desde un solo lugar.

Un empleado que trabaja en dos sedes hoy necesita **dos usuarios creados a
mano**, uno en cada sistema. Esto los crea en las que correspondan, con una sola
carga.

🔑 **Sigue habiendo N usuarios, y eso es a proposito.** No es SSO: cada
instancia mantiene su `libraauth` y su sesion. Lo que cambia es que se crean y
se dan de baja desde un lugar. La contrasena tambien sigue siendo una por sede
---replicar un cambio de contrasena es replicar un secreto, y el dia que una
instancia no conteste quedan desincronizadas sin que nadie se entere---.

🔴 **El panel entra con SU credencial, que es por instancia.** Del otro lado la
acepta `json_api_require_admin_o_servicio_o_panel` (libraauth v0.35.0), que los
productos declaran **solo** en su router de usuarios.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..cliente_sucursal import EmpleadoYaExiste, SucursalSinRespuesta
from ..deps import requiere_admin, usuario_actual

router = APIRouter(prefix="/api/empleados", tags=["empleados"])


class EmpleadoNuevo(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    #: 🔴 Viaja al alta de cada sucursal y **no se guarda en el panel**. El
    #: panel no es un almacen de contrasenas: si la guardara, un dump de su base
    #: abriria las sesiones de los empleados en todas las sedes.
    password: str = Field(min_length=8, max_length=200)
    role: str = Field(default="staff", max_length=20)
    #: En que sucursales darlo de alta. Vacio no es "en todas": es un pedido
    #: sin destino, y hacerlo en todas por omision es como se le crea un usuario
    #: en una sede donde no trabaja.
    slugs: list[str] = Field(min_length=1)


async def _alta_en_una(cliente, sucursal, datos: dict) -> dict:
    """El alta en una sucursal, con su resultado. **Nunca lanza.**

    🔴 Que una sede no conteste no puede abortar el alta en las otras: el
    empleado empieza a trabajar en las que si andan y la que fallo se reintenta.
    Lo mismo que hace el resumen con una sucursal caida.
    """
    if sucursal.problema:
        return {"slug": sucursal.slug, "nombre": sucursal.nombre,
                "estado": "sin_respuesta", "detalle": sucursal.problema}
    try:
        creado = await cliente.crear_usuario(
            url_base=sucursal.url_base, credencial=sucursal.credencial,
            ruta=sucursal.ruta_de_usuarios, datos=datos,
        )
    except EmpleadoYaExiste as e:
        # 🔑 No es una falla: es el caso normal de un empleado que ya trabajaba
        # en esa sede y ahora suma otra. Se distingue para que la pantalla no
        # lo pinte de rojo y el dueño no salga a arreglar lo que ya esta bien.
        return {"slug": sucursal.slug, "nombre": sucursal.nombre,
                "estado": "ya_estaba", "detalle": str(e)}
    except SucursalSinRespuesta as e:
        return {"slug": sucursal.slug, "nombre": sucursal.nombre,
                "estado": "sin_respuesta", "detalle": e.detalle}
    return {"slug": sucursal.slug, "nombre": sucursal.nombre,
            "estado": "creado", "detalle": creado.get("username", "")}


@router.post("", dependencies=[Depends(requiere_admin)])
async def alta(
    datos: EmpleadoNuevo,
    request: Request,
    usuario: dict = Depends(usuario_actual),
):
    """Da de alta al empleado en las sucursales pedidas, en paralelo.

    Devuelve **una fila por sucursal** con su estado, y `parcial: true` si
    alguna no contesto. Nunca devuelve un exito liso: el dueño tiene que poder
    ver en cuales quedo dado de alta y en cuales no, que es justamente lo que
    hoy no puede saber cuando los crea a mano.
    """
    registro = request.app.state.registro
    cliente = request.app.state.cliente_sucursal
    # 🔴 Se parte de las sucursales que ESTE usuario ve, no del registro entero:
    # es la misma tabla que aisla a un cliente de otro en el resumen. Un admin
    # sin asignaciones no aprovisiona en las sucursales de nadie.
    disponibles = {
        s.slug: s
        for s in registro.para_consultar(usuario["id"])
    }
    faltan = sorted(set(datos.slugs) - set(disponibles))
    if faltan:
        # 409 y no 404: el recurso de la URL existe. Y se rechaza el pedido
        # entero en vez de dar de alta en las que si estan ---un alta a medias
        # es peor que ninguna, porque parece aplicada---.
        raise HTTPException(
            409, f"Estas sucursales no existen o no las tenes asignadas: {faltan}."
        )

    cuerpo = {
        "username": datos.username.strip(), "name": datos.name.strip(),
        "password": datos.password, "role": datos.role,
    }
    resultados = list(await asyncio.gather(
        *(_alta_en_una(cliente, disponibles[slug], cuerpo) for slug in datos.slugs)
    ))
    return {
        "username": cuerpo["username"],
        "sucursales": resultados,
        "parcial": any(r["estado"] == "sin_respuesta" for r in resultados),
    }
