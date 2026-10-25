"""El bloque `club` de LibraClub: una fila por sucursal del club, sumada entre instancias.

Funciones puras, como `consolidado.py`: no hablan con nadie y se prueban sin red.

**Dos significados de «sucursal».** Para el panel, una *sucursal* es una instancia
registrada (la unidad que contesta `/api/resumen`). Para LibraClub, una sucursal
es una sede del club **dentro** de una instancia. Una instancia con tres sedes es
una sola «sucursal» del panel y tres filas de `club.por_sucursal`. Para no
confundirlas, en este modulo la primera se llama **instancia** (`slug`,
`instancia`) y la segunda **sucursal** (`sucursal_id`, `sucursal`).

Es el gate del ROADMAP de LibraClub: «un dueño con dos instancias y cinco
sucursales viendo cinco filas, no dos». Por eso la tabla sale por sucursal y las
instancias solo aportan el nombre de donde viene cada fila.

Las reglas de `consolidado.py` valen igual:

1. 🔴 **Una instancia que no contesta no entra como cero.** No tiene respuesta
   que mirar: `cobertura` (en la respuesta general) ya la nombra, y aca no
   aparece ninguna fila inventada.
2. 🔴 **Una instancia sin `club` no es una instancia con el club en cero.** Una
   instancia vieja, o de otro producto, no manda el bloque: no aporta filas ni
   baja el promedio. La respuesta dice de cuantas salio (`instancias`), para que
   la pantalla escriba «de 2 de 3 que contestaron».
3. 🔴 **Un dato que no vino no es un cero.** Un numero ausente o con forma rara
   queda `None`; no se rellena. Y una instancia con un `club` ilegible no tumba
   la respuesta de las demas: queda en `invalidos`, con el motivo.

**Cómo se suma.**

- Conteos (`reservas`, `canceladas`, `ausentes`) e ingresos: suma simple.
- `variacion_pct`: `(total - total_periodo_anterior) / total_periodo_anterior`.
  Sin periodo anterior (o en cero) no hay contra que comparar: `None`, no `+inf`.
- 🔑 **Ocupacion general: ponderada por horas.** Un porcentaje no se suma, y el promedio
  simple le da el mismo peso a una sede de 3 reservas que a una de 300. Cuando **todas**
  las filas traen `horas_abiertas` y `horas_reservadas` (numeros), la ocupacion general es
  `sum(horas_reservadas) / sum(horas_abiertas)`: es la cuenta exacta, porque la
  ocupacion de cada sede ya es esa misma razon. Si alguna fila no las trae (una instancia
  de una version anterior), **ninguna** se mezcla: cae al criterio de antes, el promedio
  ponderado por `reservas` (y, si todas tienen cero reservas, al promedio simple). Mezclar
  los dos criterios en un mismo numero no seria ni uno ni el otro. La respuesta dice cual
  uso en `criterio_ocupacion`. Una sucursal sin `ocupacion_pct` (sin horas abiertas) queda
  fuera del criterio por reservas y suma 0 horas abiertas en el criterio por horas.
- El mapa de calor combinado usa el mismo criterio por franja (dia, hora), entre las
  sucursales que informan esa franja: el peso de cada sede es su `horas_abiertas` (o sus
  `reservas`, segun el criterio). Una franja que una sucursal no manda es «sin dato», no 0 %.
- `ingresos` puede venir `null` (instancia sin base de LibraCore): queda todo en `None`, se ve
  «—» y no suma como 0.
- `origen`: suma por clave, con las claves que vengan (pueden variar).
"""

import datetime
import math

#: Claves de `ingresos` que se suman. El resto de lo que mande la instancia se ignora.
CLAVES_INGRESOS = ("reservas", "senas", "buffet", "total", "total_periodo_anterior")

#: Criterios de la ocupacion general, para que la pantalla lo diga con todas las letras.
CRITERIO_HORAS = "ponderada_por_horas"
CRITERIO_RESERVAS = "ponderada_por_reservas"


def _numero(valor) -> float | int | None:
    """El numero, o `None` si no es uno usable.

    Los `bool` se descartan aunque en Python sean `int`, y los `NaN`/`inf` tambien:
    un `inf` en una suma envenena el total y revienta el `json` de la respuesta.
    """
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    return valor


def _entero(valor) -> int | None:
    n = _numero(valor)
    return None if n is None else int(n)


def _redondear(valor: float | None, decimales: int = 1) -> float | None:
    return None if valor is None else round(valor, decimales)


def variacion_pct(total, anterior) -> float | None:
    """Variacion porcentual contra el periodo anterior, o `None` si no hay base."""
    total, anterior = _numero(total), _numero(anterior)
    if total is None or anterior is None or anterior <= 0:
        return None
    return _redondear((total - anterior) / anterior * 100)


def promedio_ponderado(pares: list[tuple[float, float]]) -> float | None:
    """Promedio de `(valor, peso)`. Sin pesos positivos, promedio simple. Vacio, `None`."""
    if not pares:
        return None
    peso_total = sum(peso for _, peso in pares)
    if peso_total > 0:
        return sum(valor * peso for valor, peso in pares) / peso_total
    return sum(valor for valor, _ in pares) / len(pares)


def _franjas(crudas) -> list[dict]:
    """Las franjas validas (`dia` 0-6, `hora` 0-23, ocupacion numerica), sin repetir."""
    por_celda: dict[tuple[int, int], float] = {}
    if not isinstance(crudas, list):
        return []
    for f in crudas:
        if not isinstance(f, dict):
            continue
        dia, hora, pct = _entero(f.get("dia")), _entero(f.get("hora")), _numero(f.get("ocupacion_pct"))
        if dia is None or hora is None or pct is None or not (0 <= dia <= 6 and 0 <= hora <= 23):
            continue
        por_celda[(dia, hora)] = pct
    return [
        {"dia": dia, "hora": hora, "ocupacion_pct": _redondear(pct)}
        for (dia, hora), pct in sorted(por_celda.items())
    ]


def _origen(crudo) -> dict[str, float | int]:
    """`{clave: cantidad}` tal como vino, descartando lo que no sea numero."""
    if not isinstance(crudo, dict):
        return {}
    salida = {}
    for clave, valor in crudo.items():
        n = _numero(valor)
        if n is not None:
            salida[str(clave)] = n
    return salida


def _ingresos(crudo) -> dict[str, float | int | None]:
    crudo = crudo if isinstance(crudo, dict) else {}
    return {clave: _numero(crudo.get(clave)) for clave in CLAVES_INGRESOS}


def _fecha(valor) -> str | None:
    """La fecha ISO (`aaaa-mm-dd`), o `None` si no lo es."""
    if not isinstance(valor, str):
        return None
    try:
        return datetime.date.fromisoformat(valor).isoformat()
    except ValueError:
        return None


def _fila(slug: str, instancia: str, cruda) -> dict | None:
    """Una sucursal del club como fila del panel, o `None` si no es un objeto."""
    if not isinstance(cruda, dict):
        return None
    ingresos = _ingresos(cruda.get("ingresos"))
    return {
        "slug": slug,
        "instancia": instancia,
        "sucursal_id": cruda.get("sucursal_id"),
        "sucursal": str(cruda.get("sucursal") or ""),
        "ocupacion_pct": _redondear(_numero(cruda.get("ocupacion_pct"))),
        "reservas": _entero(cruda.get("reservas")),
        "horas_abiertas": _numero(cruda.get("horas_abiertas")),
        "horas_reservadas": _numero(cruda.get("horas_reservadas")),
        "canceladas": _entero(cruda.get("canceladas")),
        "ausentes": _entero(cruda.get("ausentes")),
        "ingresos": ingresos,
        "variacion_pct": variacion_pct(ingresos["total"], ingresos["total_periodo_anterior"]),
        "origen": _origen(cruda.get("origen")),
        "franjas": _franjas(cruda.get("franjas")),
    }


def _sumar(filas: list[dict], clave: str) -> int | None:
    valores = [f[clave] for f in filas if f[clave] is not None]
    return sum(valores) if valores else None


def _criterio(filas: list[dict]) -> str:
    """`ponderada_por_horas` si TODAS las filas traen las dos columnas de horas."""
    if filas and all(f["horas_abiertas"] is not None and f["horas_reservadas"] is not None for f in filas):
        return CRITERIO_HORAS
    return CRITERIO_RESERVAS


def _peso(fila: dict, criterio: str) -> float:
    return (fila["horas_abiertas"] if criterio == CRITERIO_HORAS else fila["reservas"]) or 0


def _ocupacion_general(filas: list[dict], criterio: str) -> float | None:
    if criterio == CRITERIO_HORAS:
        abiertas = sum(f["horas_abiertas"] for f in filas)
        if abiertas <= 0:
            return None
        return _redondear(sum(f["horas_reservadas"] for f in filas) / abiertas * 100)
    return _redondear(promedio_ponderado(
        [(f["ocupacion_pct"], f["reservas"] or 0) for f in filas if f["ocupacion_pct"] is not None]
    ))


def _franjas_combinadas(filas: list[dict], criterio: str) -> list[dict]:
    """Cada franja, ponderada (horas abiertas o reservas) por las sucursales que la informan."""
    por_celda: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for f in filas:
        peso = _peso(f, criterio)
        for franja in f["franjas"]:
            por_celda.setdefault((franja["dia"], franja["hora"]), []).append(
                (franja["ocupacion_pct"], peso)
            )
    return [
        {
            "dia": dia,
            "hora": hora,
            "ocupacion_pct": _redondear(promedio_ponderado(pares)),
            # De cuantas sucursales sale la celda: no todas abren a la misma hora.
            "sucursales": len(pares),
        }
        for (dia, hora), pares in sorted(por_celda.items())
    ]


def totales(filas: list[dict]) -> dict:
    """Los totales generales de un conjunto de filas."""
    ingresos = {}
    for clave in CLAVES_INGRESOS:
        valores = [f["ingresos"][clave] for f in filas if f["ingresos"][clave] is not None]
        ingresos[clave] = sum(valores) if valores else None
    origen: dict[str, float | int] = {}
    for f in filas:
        for clave, cantidad in f["origen"].items():
            origen[clave] = origen.get(clave, 0) + cantidad
    criterio = _criterio(filas)
    return {
        "sucursales": len(filas),
        "ocupacion_pct": _ocupacion_general(filas, criterio),
        "criterio_ocupacion": criterio,
        "reservas": _sumar(filas, "reservas"),
        "canceladas": _sumar(filas, "canceladas"),
        "ausentes": _sumar(filas, "ausentes"),
        "ingresos": ingresos,
        "variacion_pct": variacion_pct(ingresos["total"], ingresos["total_periodo_anterior"]),
        "origen": origen,
    }


def armar_club(reportes: list[tuple[str, str, dict | None]]) -> dict | None:
    """El bloque `club` de la respuesta, o `None` si ninguna instancia lo manda.

    `reportes` es `(slug, nombre, datos)` de **las instancias que contestaron**,
    en el orden del registro; `datos` es el cuerpo tal cual lo mando la instancia.
    """
    filas: list[dict] = []
    slugs: list[str] = []
    invalidos: list[dict] = []
    periodos: set[tuple[str, str]] = set()
    for slug, nombre, datos in reportes:
        if not isinstance(datos, dict) or "club" not in datos:
            continue
        club = datos["club"]
        sucursales = club.get("por_sucursal") if isinstance(club, dict) else None
        if not isinstance(sucursales, list):
            # La instancia dijo tener club pero no en la forma del contrato: se
            # nombra, y las demas siguen.
            invalidos.append({
                "slug": slug,
                "nombre": nombre,
                "detalle": "El bloque club no trae `por_sucursal` como lista.",
            })
            continue
        slugs.append(slug)
        desde, hasta = _fecha(club.get("desde")), _fecha(club.get("hasta"))
        if desde and hasta:
            periodos.add((desde, hasta))
        for cruda in sucursales:
            fila = _fila(slug, nombre, cruda)
            if fila is not None:
                filas.append(fila)

    if not slugs and not invalidos:
        return None

    return {
        # El periodo que las instancias dicen haber calculado (`club.desde` /
        # `club.hasta`), que es el que se lee en pantalla. Si dos instancias
        # contestaron periodos distintos, se toma el rango que los cubre y
        # `periodo_uniforme` lo dice: esos numeros no son del mismo periodo.
        "desde": min((d for d, _ in periodos), default=None),
        "hasta": max((h for _, h in periodos), default=None),
        "periodo_uniforme": len(periodos) <= 1,
        # De cuantas instancias salio: puede ser menos que las que contestaron.
        "instancias": len(slugs),
        "slugs": slugs,
        "invalidos": invalidos,
        "por_sucursal": filas,
        "totales": totales(filas),
        "franjas": _franjas_combinadas(filas, _criterio(filas)),
    }
