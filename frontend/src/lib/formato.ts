// Cómo se leen los números del panel.
//
// Está separado de `fecha.ts` porque son dos cosas distintas, y en un módulo y
// no inline en cada tarjeta por la misma razón: un `toLocaleString` copiado en
// N vistas termina divergiendo.

const PESOS = new Intl.NumberFormat('es-AR', {
  style: 'currency', currency: 'ARS', maximumFractionDigits: 2,
})

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
  return esPlata(clave) ? PESOS.format(valor) : ENTEROS.format(valor)
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
