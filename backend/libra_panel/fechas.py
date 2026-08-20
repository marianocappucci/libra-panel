"""Fecha y hora del panel. **Un solo lugar**, para todo el producto.

Estandar de la familia desde el 2026-08-12: huso horario de Argentina, UTC-3
fijo y sin horario de verano, y fechas a la vista en `dd-mm-aaaa`. Ver
`wiki/concepts/estandares-desarrollo.md`, seccion "Fecha y hora".

**El formato es solo de presentacion.** Lo que sale por la API y lo que viaja
en las URLs va en ISO 8601 — incluido el `?desde=&hasta=` que este panel le
manda a cada sucursal, que es una conversacion entre maquinas. El backend
formatea `dd-mm-aaaa` unicamente para textos que lee una persona; el resto lo
formatea el frontend con su propio helper unico (`src/lib/fecha.ts`).

Que este en un modulo propio y no repetido por vista es la parte que importa:
una constante de zona copiada en N lugares es divergencia esperando a pasar.
"""
import datetime

#: UTC-3 fijo, sin DST. Misma definicion que `_AR_TZ` de `libracore.db.core`.
#: Se declara como offset y no como zona IANA a proposito: Argentina no aplica
#: horario de verano, y un offset fijo no depende de que la imagen del
#: contenedor tenga la base de datos de zonas instalada.
AR_TZ = datetime.timezone(datetime.timedelta(hours=-3), name="ART")


def ahora_ar() -> datetime.datetime:
    """El instante actual en hora de Argentina."""
    return datetime.datetime.now(AR_TZ)


def hoy_ar() -> datetime.date:
    """El dia de hoy en Argentina.

    🔴 No es `date.today()`. Entre las 21:00 y la medianoche de Argentina, una
    maquina en UTC ya esta en el dia siguiente: el panel pediria "el mes en
    curso" arrancando el 1 del mes que viene y mostraria todo en cero. Es
    exactamente el tipo de cero que este producto existe para no mostrar.
    """
    return ahora_ar().date()


def rango_por_defecto() -> tuple[str, str]:
    """El mes en curso, en ISO. Es el periodo que se usa si no se pide otro."""
    hoy = hoy_ar()
    return hoy.replace(day=1).isoformat(), hoy.isoformat()


def a_dd_mm_aaaa(valor: datetime.date | str) -> str:
    """`2026-08-20` -> `20-08-2026`. Para texto que lee una persona.

    Acepta la fecha ya en ISO porque asi es como viaja por la API. Un valor que
    no parsea se devuelve tal cual en vez de reventar: esto formatea, no
    valida — la validacion del periodo la hace el router, que puede contestar
    un 422 con sentido.
    """
    if isinstance(valor, str):
        try:
            valor = datetime.date.fromisoformat(valor)
        except ValueError:
            return valor
    return valor.strftime("%d-%m-%Y")
