import { describe, expect, it } from 'vitest'

import { aDdMmAaaa, hoyIso, periodoLegible, primerDiaDelMesIso } from '../lib/fecha'
import { etiqueta, formatearValor, metricasDe } from '../lib/formato'

describe('fecha', () => {
  it('muestra dd-mm-aaaa y no ISO', () => {
    expect(aDdMmAaaa('2026-08-20')).toBe('20-08-2026')
  })

  it('🔴 no se corre un día al formatear', () => {
    // `new Date('2026-08-01')` es medianoche UTC; mostrado en UTC-3 da el 31 de
    // julio. Por eso se parte la cadena en vez de construir un `Date`.
    expect(aDdMmAaaa('2026-08-01')).toBe('01-08-2026')
    expect(aDdMmAaaa('2026-01-01')).toBe('01-01-2026')
  })

  it('devuelve tal cual lo que no es una fecha', () => {
    expect(aDdMmAaaa('')).toBe('')
    expect(aDdMmAaaa('sin fecha')).toBe('sin fecha')
  })

  it('arma el período legible', () => {
    expect(periodoLegible('2026-08-01', '2026-08-20')).toBe('01-08-2026 al 20-08-2026')
  })

  it('hoy y el primero del mes salen en ISO, que es lo que come el input date', () => {
    expect(hoyIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(primerDiaDelMesIso()).toMatch(/^\d{4}-\d{2}-01$/)
    expect(primerDiaDelMesIso().slice(0, 7)).toBe(hoyIso().slice(0, 7))
  })
})

describe('formato de números', () => {
  it('la plata sale como plata y las cantidades no', () => {
    expect(formatearValor('facturado', 1234.5)).toContain('$')
    expect(formatearValor('comprobantes', 12)).toBe('12')
  })

  it('el monto anidado también es plata', () => {
    expect(formatearValor('monto', 100)).toContain('$')
  })

  it('una clave desconocida se muestra prolija en vez de esconderse', () => {
    expect(etiqueta('turnos_sin_confirmar')).toBe('Turnos sin confirmar')
  })
})

describe('métricas de un bloque', () => {
  it('aplana lo anidado con la ruta como etiqueta', () => {
    const m = metricasDe({ sin_cobrar: { cantidad: 2, monto: 20 } })
    expect(m.map((x) => x.etiqueta)).toEqual(['Sin cobrar · Cantidad', 'Sin cobrar · Monto'])
  })

  it('descarta lo que no es número', () => {
    // Un `moneda: "ARS"` o un `activo: true` no son métricas: sumarlos o
    // dibujarlos como tarjeta no significa nada.
    const m = metricasDe({ moneda: 'ARS', activo: true, monto: 5 })
    expect(m.map((x) => x.clave)).toEqual(['monto'])
  })
})
