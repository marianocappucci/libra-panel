"""La suma. Funciones puras: no habla con nadie, se prueba sin red.

Tres reglas gobiernan este modulo, y las tres existen para que el panel no
muestre un numero mas chico que la realidad con cara de numero correcto:

1. 🔴 **Una sucursal que no contesta NO es una sucursal que vendio cero.** El
   total sale siempre con el conteo al lado —"4 de 5 sucursales"— y marcado
   como parcial cuando falta alguna, no solo cuando el que mira pregunta.

2. 🔴 **Un bloque que no aplica NO es un bloque en cero.** Una sucursal de
   MedLibra no tiene ventas de buffet: sumar `0` ahi dice "no vendieron nada"
   cuando lo cierto es "esto no se mide aca". Cada bloque lleva de cuantas
   sucursales salio, y un bloque que no reporto ninguna no aparece.

3. 🔴 **Sumar entre CUITs da un numero de gestion, no uno fiscal.** El
   consolidado por razon social esta al lado del general, porque es el unico
   que cierra contra los libros.

Ver `wiki/analyses/panel-del-dueno-multisucursal.md`, puntos 3 y 9.
"""
import re
from dataclasses import dataclass, field

#: Claves de la respuesta de una sucursal que **no** son bloques de numeros.
#: Todo lo demas que mande la sucursal se trata como bloque y se suma, para que
#: un producto que agregue el bloque `agenda` de LibraGenda aparezca en el
#: panel sin tocar este archivo.
NO_SON_BLOQUES = frozenset({"instancia", "periodo"})


@dataclass(frozen=True)
class ResultadoSucursal:
    """Lo que se supo de una sucursal en esta consulta."""

    slug: str
    nombre: str
    #: CUIT y razon social **del registro del panel**, no de la respuesta. Son
    #: los que agrupan, porque una sucursal caida no tiene respuesta que mirar
    #: y aun asi tiene que caer en su grupo — y el grupo, quedar marcado como
    #: parcial.
    cuit: str = ""
    razon_social: str = ""
    ok: bool = False
    detalle: str = ""
    #: El cuerpo tal cual lo mando la sucursal. `None` si no contesto.
    datos: dict | None = field(default=None)


def normalizar_cuit(cuit: str) -> str:
    """Solo los digitos. `30-71234567-9` y `30712345679` son el mismo CUIT.

    Sin esto, la misma razon social cargada con guiones en una sucursal y sin
    guiones en otra saldria como dos grupos, y cada uno mostraria la mitad de
    los numeros de la empresa.
    """
    return re.sub(r"\D", "", cuit or "")


# ── Suma ────────────────────────────────────────────────────────────────────


def _hojas(dato, prefijo: tuple = ()) -> dict[tuple, float]:
    """Aplana un bloque a `ruta -> numero`, ignorando lo que no sea numero.

    Los `bool` se descartan explicitamente aunque en Python sean `int`: una
    bandera `activo: true` sumada cinco veces daria `5`, que no es un total de
    nada.
    """
    hojas: dict[tuple, float] = {}
    if isinstance(dato, dict):
        for clave, valor in dato.items():
            hojas.update(_hojas(valor, prefijo + (str(clave),)))
    elif isinstance(dato, bool):
        pass
    elif isinstance(dato, (int, float)):
        hojas[prefijo] = dato
    return hojas


def _anidar(hojas: dict[tuple, float]) -> dict:
    """El inverso de `_hojas`: reconstruye la forma original con los totales."""
    salida: dict = {}
    for ruta, valor in hojas.items():
        cursor = salida
        for parte in ruta[:-1]:
            cursor = cursor.setdefault(parte, {})
        cursor[ruta[-1]] = valor
    return salida


def sumar_bloque(cuerpos: list[dict]) -> dict:
    """Suma N versiones del mismo bloque y dice de donde salio cada numero.

    `incompletos` son las rutas que **no** estaban en todas las sucursales que
    reportaron el bloque. Es el caso de un producto que manda `comercio` sin
    `stock_bajo_minimo`: el total de ese campo saldria de menos sucursales que
    el resto del bloque, y sin decirlo pareceria salir de todas.
    """
    totales: dict[tuple, float] = {}
    aportantes: dict[tuple, int] = {}
    for cuerpo in cuerpos:
        for ruta, valor in _hojas(cuerpo).items():
            totales[ruta] = totales.get(ruta, 0) + valor
            aportantes[ruta] = aportantes.get(ruta, 0) + 1
    incompletos = sorted(
        ".".join(ruta) for ruta, cuantas in aportantes.items() if cuantas < len(cuerpos)
    )
    return {"datos": _anidar(totales), "incompletos": incompletos}


def bloques_de(datos: dict | None) -> dict[str, dict]:
    """Los bloques de numeros de una respuesta, sin la identidad ni el periodo."""
    if not datos:
        return {}
    return {
        clave: valor
        for clave, valor in datos.items()
        if clave not in NO_SON_BLOQUES and isinstance(valor, dict)
    }


def consolidar(resultados: list[ResultadoSucursal]) -> dict:
    """El total de un conjunto de sucursales, con su cobertura al lado.

    La cobertura **va siempre**, no solo cuando falla alguna: un contador que
    aparece unicamente ante un problema entrena a no mirarlo, y el dia que
    aparece nadie lo lee.
    """
    respondieron = [r for r in resultados if r.ok]
    sin_respuesta = [
        {"slug": r.slug, "nombre": r.nombre, "detalle": r.detalle}
        for r in resultados
        if not r.ok
    ]

    por_bloque: dict[str, list[dict]] = {}
    slugs_por_bloque: dict[str, list[str]] = {}
    for r in respondieron:
        for nombre, cuerpo in bloques_de(r.datos).items():
            por_bloque.setdefault(nombre, []).append(cuerpo)
            slugs_por_bloque.setdefault(nombre, []).append(r.slug)

    bloques = {}
    for nombre, cuerpos in por_bloque.items():
        suma = sumar_bloque(cuerpos)
        bloques[nombre] = {
            "datos": suma["datos"],
            # De cuantas sucursales salio ESTE bloque. Puede ser menor que
            # `respondieron` sin que nada este mal: significa que las otras no
            # lo miden. Un bloque que nadie reporto no esta en este diccionario.
            "sucursales": len(cuerpos),
            "slugs": slugs_por_bloque[nombre],
            "incompletos": suma["incompletos"],
        }

    return {
        "cobertura": {
            "total": len(resultados),
            "respondieron": len(respondieron),
            # `parcial` es un campo y no algo que deduzca la pantalla: es la
            # bandera que decide si el numero se puede leer como el total.
            "parcial": bool(sin_respuesta),
            "sin_respuesta": sin_respuesta,
        },
        "bloques": bloques,
    }


# ── Agrupacion por razon social ─────────────────────────────────────────────


def agrupar_por_cuit(resultados: list[ResultadoSucursal]) -> list[dict]:
    """Un grupo por razon social, mas las sucursales sin identificar sueltas.

    🔴 **El CUIT vacio no agrupa.** Medido el 2026-08-20 contra la instancia
    demo, que contesto `instancia: '' CUIT '' PV None` porque no tiene empresa
    configurada: con el CUIT vacio como clave, dos sucursales sin configurar se
    juntarian como si fueran la misma empresa — y con cualquier otra vacia que
    apareciera despues. Un dato faltante se ve; uno agrupado mal, no.

    Se agrupa por el CUIT **del registro** y no por el que informa la sucursal,
    para que una sucursal caida caiga igual en su grupo y el grupo salga
    marcado como parcial. Cuando los dos existen y no coinciden, la fila de la
    sucursal lo dice (`cuit_discrepa`).
    """
    grupos: dict[str, list[ResultadoSucursal]] = {}
    sueltas: list[ResultadoSucursal] = []
    for r in resultados:
        clave = normalizar_cuit(r.cuit)
        if clave:
            grupos.setdefault(clave, []).append(r)
        else:
            sueltas.append(r)

    salida = []
    for clave, miembros in grupos.items():
        salida.append(
            {
                "clave": f"cuit:{clave}",
                "identificado": True,
                "cuit": next((m.cuit for m in miembros if m.cuit), ""),
                "razon_social": next(
                    (m.razon_social for m in miembros if m.razon_social), ""
                ),
                "sucursales": [m.slug for m in miembros],
                **consolidar(miembros),
            }
        )
    for r in sueltas:
        salida.append(
            {
                "clave": f"sucursal:{r.slug}",
                # La pantalla la muestra aparte y nombrada, nunca sumada con
                # otra sin identificar.
                "identificado": False,
                "cuit": "",
                "razon_social": r.razon_social or r.nombre,
                "sucursales": [r.slug],
                **consolidar([r]),
            }
        )
    # Identificados primero y por razon social; las sin identificar al final,
    # que es donde se leen como pendiente de configurar y no como un grupo mas.
    salida.sort(key=lambda g: (not g["identificado"], g["razon_social"].lower()))
    return salida


# ── Respuesta completa ──────────────────────────────────────────────────────


def _fila_de_sucursal(r: ResultadoSucursal) -> dict:
    identidad = (r.datos or {}).get("instancia") or {}
    informado = str(identidad.get("cuit") or "")
    return {
        "slug": r.slug,
        "nombre": r.nombre,
        "cuit": r.cuit,
        "razon_social": r.razon_social,
        "estado": "ok" if r.ok else "sin_respuesta",
        "detalle": r.detalle,
        # Lo que la sucursal dice ser, para poder contrastarlo con el registro.
        "identidad": {
            "nombre": str(identidad.get("nombre") or ""),
            "cuit": informado,
            "punto_venta": identidad.get("punto_venta"),
        },
        # 🔴 La sucursal contesto pero no sabe quien es: no tiene empresa
        # configurada. No rompe la suma, pero rompe el supuesto de que el CUIT
        # identifica la razon social, asi que se muestra.
        "identidad_incompleta": bool(r.ok and not informado),
        # El registro dice un CUIT y la sucursal informa otro. Uno de los dos
        # esta mal y el consolidado por razon social sale mal por el medio.
        "cuit_discrepa": bool(
            informado
            and r.cuit
            and normalizar_cuit(informado) != normalizar_cuit(r.cuit)
        ),
        "bloques": bloques_de(r.datos),
    }


def armar_respuesta(*, desde: str, hasta: str, resultados: list[ResultadoSucursal]) -> dict:
    """Todo lo que necesita la pantalla, en una sola respuesta."""
    general = consolidar(resultados)
    return {
        "periodo": {"desde": desde, "hasta": hasta},
        "cobertura": general["cobertura"],
        "consolidado": general["bloques"],
        "grupos": agrupar_por_cuit(resultados),
        "sucursales": [_fila_de_sucursal(r) for r in resultados],
    }
