// Cómo se leen los números del panel.
//
// Está separado de `fecha.ts` porque son dos cosas distintas, y en un módulo y
// no inline en cada tarjeta por la misma razón: un `toLocaleString` copiado en
// N vistas termina divergiendo.

import { formatoMoneda } from 'libra-ui/formatos'

// La plata sale del formateador común del kit (libra-ui/formatos, ADR-050); los conteos siguen siendo enteros.
const ENTEROS = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 })

/** Claves que son plata. El resto son cantidades. */
const SON_PLATA = new Set([
  'facturado', 'cobrado', 'egresos', 'saldo_caja', 'monto',
])

export function esPlata(clave: string): boolean {
  return SON_PLATA.has(clave)
}

export function formatearValor(clave: string, valor: unknown): string {
  if (typeof valor !== 'number') return String(valor ?? '—')
  return esPlata(clave) ? formatoMoneda(valor) : ENTEROS.format(valor)
}

/** Etiquetas legibles. Una clave desconocida se muestra tal cual, prolija.
 *
 * 🔴 **Sin `default` que la esconda**: si un motor agrega un bloque nuevo, el
 * panel tiene que mostrarlo aunque no sepa cómo se llama en castellano. Una
 * lista blanca haría desaparecer de la pantalla un número que la sucursal sí
 * mandó, que es la peor forma de no saber algo.
 */
const ETIQUETAS: Record<string, string> = {
  facturado: 'Facturado',
  cobrado: 'Cobrado',
  egresos: 'Egresos',
  saldo_caja: 'Saldo de caja',
  comprobantes: 'Comprobantes',
  sin_cobrar: 'Sin cobrar',
  cantidad: 'Cantidad',
  monto: 'Monto',
  ventas: 'Ventas',
  stock_bajo_minimo: 'Stock bajo mínimo',
  turnos: 'Turnos',
  nucleo: 'Facturación y caja',
  comercio: 'Ventas y stock',
  agenda: 'Agenda',
}

export function etiqueta(clave: string): string {
  if (ETIQUETAS[clave]) return ETIQUETAS[clave]
  const limpio = clave.replace(/_/g, ' ')
  return limpio.charAt(0).toUpperCase() + limpio.slice(1)
}

export type Metrica = { ruta: string; clave: string; etiqueta: string; valor: number }

/** Aplana un bloque a la lista de métricas que se dibujan como tarjetas.
 *
 * `sin_cobrar: {cantidad, monto}` sale como dos métricas —"Sin cobrar ·
 * Cantidad" y "Sin cobrar · Monto"— en vez de una sola inventada.
 */
export function metricasDe(datos: Record<string, unknown>, prefijo: string[] = []): Metrica[] {
  const salida: Metrica[] = []
  for (const [clave, valor] of Object.entries(datos ?? {})) {
    const ruta = [...prefijo, clave]
    if (valor !== null && typeof valor === 'object' && !Array.isArray(valor)) {
      salida.push(...metricasDe(valor as Record<string, unknown>, ruta))
    } else if (typeof valor === 'number') {
      salida.push({
        ruta: ruta.join('.'),
        clave,
        etiqueta: ruta.map(etiqueta).join(' · '),
        valor,
      })
    }
  }
  return salida
}

// ── LibraClub ───────────────────────────────────────────────────────────────

const UN_DECIMAL = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

/** `66,5 %`. Un dato que no vino (`null`) sale como «—», nunca como `0 %`. */
export function formatearPorcentaje(valor: number | null | undefined): string {
  return typeof valor === 'number' ? `${UN_DECIMAL.format(valor)} %` : '—'
}

/** `+23,8 %` / `−9,1 %`. Sin período anterior con qué comparar, «—». */
export function formatearVariacion(valor: number | null | undefined): string {
  if (typeof valor !== 'number') return '—'
  const signo = valor > 0 ? '+' : valor < 0 ? '−' : ''
  return `${signo}${UN_DECIMAL.format(Math.abs(valor))} %`
}

/** Un conteo que puede no haber venido. */
export function formatearConteo(valor: number | null | undefined): string {
  return typeof valor === 'number' ? ENTEROS.format(valor) : '—'
}

/** Plata que puede no haber venido. */
export function formatearPlata(valor: number | null | undefined): string {
  return typeof valor === 'number' ? formatoMoneda(valor) : '—'
}

/** 0 = lunes … 6 = domingo, como lo manda LibraClub. */
export const DIAS_CORTOS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
export const DIAS_LARGOS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']

/** De dónde vino la reserva. Una clave que no se conoce sale prolija (`etiqueta`),
 * nunca escondida: las claves de `origen` las manda cada instancia. */
const ORIGENES: Record<string, string> = {
  mostrador: 'Mostrador',
  portal: 'Portal web',
  whatsapp: 'WhatsApp',
  telefono: 'Teléfono',
  serie: 'Turno fijo (serie)',
}

export function etiquetaDeOrigen(clave: string): string {
  return ORIGENES[clave] ?? etiqueta(clave)
}
