// Los bloques y sus denominadores propios.
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Bloque } from '../api'
import { Consolidado, TarjetasDeBloque } from '../components/Bloques'

const NUCLEO: Bloque = {
  datos: { facturado: 400, cobrado: 320, sin_cobrar: { cantidad: 8, monto: 80 } },
  sucursales: 4,
  slugs: ['c1', 'c2', 'c3', 'c4'],
  incompletos: [],
}

const COMERCIO: Bloque = {
  datos: { ventas: { cantidad: 12, monto: 1200 }, stock_bajo_minimo: 3 },
  sucursales: 2,
  slugs: ['c1', 'c2'],
  incompletos: [],
}

describe('un bloque', () => {
  it('dibuja una tarjeta por número, incluidos los anidados', () => {
    render(<TarjetasDeBloque nombre="nucleo" bloque={NUCLEO} respondieron={4} />)
    expect(screen.getByText('Facturado')).toBeInTheDocument()
    // `sin_cobrar` sale como DOS métricas y no como una sola inventada.
    expect(screen.getByText('Sin cobrar · Cantidad')).toBeInTheDocument()
    expect(screen.getByText('Sin cobrar · Monto')).toBeInTheDocument()
  })

  it('no aclara nada cuando salió de todas las que contestaron', () => {
    render(<TarjetasDeBloque nombre="nucleo" bloque={NUCLEO} respondieron={4} />)
    expect(screen.queryByTestId('leyenda-bloque-parcial')).toBeNull()
  })

  it('🔴 avisa cuando salió de menos sucursales que las que contestaron', () => {
    // Una sucursal de MedLibra no mide ventas de buffet. Sin esta leyenda, el
    // total de comercio se leería como si saliera de las cuatro.
    render(<TarjetasDeBloque nombre="comercio" bloque={COMERCIO} respondieron={4} />)
    expect(screen.getByTestId('leyenda-bloque-parcial')).toHaveTextContent(
      'de 2 de 4 que contestaron',
    )
  })

  it('avisa cuando una clave no la informan todas las que sí mandaron el bloque', () => {
    render(
      <TarjetasDeBloque
        nombre="comercio"
        bloque={{ ...COMERCIO, incompletos: ['stock_bajo_minimo'] }}
        respondieron={2}
      />,
    )
    expect(screen.getByTestId('aviso-incompletos')).toHaveTextContent('Stock bajo mínimo')
  })

  it('muestra una clave que no conoce en vez de esconderla', () => {
    // Si un motor agrega un bloque nuevo, el panel tiene que mostrarlo aunque
    // no sepa cómo se llama en castellano. Una lista blanca haría desaparecer
    // de la pantalla un número que la sucursal sí mandó.
    render(
      <TarjetasDeBloque
        nombre="agenda"
        bloque={{ datos: { turnos_sin_confirmar: 5 }, sucursales: 1, slugs: ['c1'], incompletos: [] }}
        respondieron={1}
      />,
    )
    expect(screen.getByText('Turnos sin confirmar')).toBeInTheDocument()
  })
})

describe('el consolidado', () => {
  it('pone la facturación y caja primero', () => {
    render(<Consolidado bloques={{ comercio: COMERCIO, nucleo: NUCLEO }} respondieron={4} />)
    const secciones = screen.getAllByRole('heading', { level: 3 })
    expect(secciones[0]).toHaveTextContent('Facturación y caja')
  })

  it('🔴 sin bloques NO dibuja un total en cero', () => {
    // Si ninguna sucursal contestó, no hay de dónde sacar el número: un `$ 0`
    // sería una invención perfectamente creíble.
    render(<Consolidado bloques={{}} respondieron={0} />)
    expect(screen.getByTestId('sin-datos')).toHaveTextContent('ninguna sucursal contestó')
    expect(screen.queryByText('$ 0,00')).toBeNull()
  })
})
