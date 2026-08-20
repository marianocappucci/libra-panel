// Fecha y hora del frontend. **Un solo lugar**, para todo el panel.
//
// Estándar de la familia desde el 2026-08-12: huso horario de Argentina
// (UTC-3 fijo, sin horario de verano) y fechas a la vista en `dd-mm-aaaa`.
//
// 🔴 **El formato es sólo de presentación.** Lo que viaja por la API va en ISO
// 8601 —incluido el `?desde=&hasta=` del resumen— y los `<input type="date">`
// no se tocan: usan el formato local del navegador y hablan ISO por su
// `value`. Lo que se formatea acá es lo que lee una persona.
//
// Que esté en un módulo y no repetido por pantalla es la parte que importa: un
// `toLocaleDateString` copiado en N vistas es divergencia esperando a pasar.

/** UTC-3 fijo. Argentina no aplica horario de verano. */
export const ZONA = 'America/Argentina/Buenos_Aires'

/** `2026-08-20` → `20-08-2026`. Acepta la fecha ISO tal como viene de la API. */
export function aDdMmAaaa(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  // Se parte la cadena en vez de construir un `Date`: `new Date('2026-08-20')`
  // se interpreta como medianoche UTC y al mostrarlo en UTC-3 devuelve el 19.
  // Es el corrimiento de un día que aparece siempre que una fecha sin hora pasa
  // por un `Date`.
  if (!m) return iso
  return `${m[3]}-${m[2]}-${m[1]}`
}

/** El período tal como se lee en pantalla: `01-08-2026 al 20-08-2026`. */
export function periodoLegible(desde: string, hasta: string): string {
  return `${aDdMmAaaa(desde)} al ${aDdMmAaaa(hasta)}`
}

/** Hoy en Argentina, en ISO. Es lo que va en el `value` de un input date. */
export function hoyIso(): string {
  // `en-CA` da `aaaa-mm-dd`, que es ISO. Se usa el formateador con zona en vez
  // de `toISOString()` porque aquél devuelve UTC: entre las 21:00 y la
  // medianoche de Argentina daría el día siguiente.
  return new Date().toLocaleDateString('en-CA', { timeZone: ZONA })
}

/** El primer día del mes en curso, en Argentina, en ISO. */
export function primerDiaDelMesIso(): string {
  return `${hoyIso().slice(0, 7)}-01`
}
