// La pantalla entera, con la API doblada.
//
// Lo que se prueba no es que dibuje tarjetas: es que un total parcial llegue a
// los ojos del dueño **marcado**, y que las sucursales sin CUIT aparezcan
// sueltas y nombradas en vez de juntas.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Resumen } from '../api'

const resumenMock = vi.fn()

vi.mock('../api', async (importOriginal) => {
  const real = await importOriginal<typeof import('../api')>()
  return { ...real, panel: { ...real.panel, resumen: resumenMock } }
})

const { Panel } = await import('../pages/Panel')

function nucleo(facturado: number) {
  return { facturado, cobrado: facturado, comprobantes: 1 }
}

const CUATRO_DE_CINCO: Resumen = {
  periodo: { desde: '2026-08-01', hasta: '2026-08-20' },
  cobertura: {
    total: 5,
    respondieron: 4,
    parcial: true,
    sin_respuesta: [{ slug: 'c5', nombre: 'Complejo Cinco', detalle: 'ConnectTimeout' }],
  },
  consolidado: {
    nucleo: { datos: nucleo(400), sucursales: 4, slugs: ['c1', 'c2', 'c3', 'c4'], incompletos: [] },
  },
  grupos: [
    {
      clave: 'cuit:30111111119',
      identificado: true,
      cuit: '30-11111111-9',
      razon_social: 'Pádel SA',
      sucursales: ['c1', 'c2'],
      cobertura: { total: 2, respondieron: 2, parcial: false, sin_respuesta: [] },
      bloques: { nucleo: { datos: nucleo(200), sucursales: 2, slugs: ['c1', 'c2'], incompletos: [] } },
    },
    {
      clave: 'sucursal:c5',
      identificado: false,
      cuit: '',
      razon_social: 'Complejo Cinco',
      sucursales: ['c5'],
      cobertura: {
        total: 1, respondieron: 0, parcial: true,
        sin_respuesta: [{ slug: 'c5', nombre: 'Complejo Cinco', detalle: 'ConnectTimeout' }],
      },
      bloques: {},
    },
  ],
  sucursales: [
    {
      slug: 'c1', nombre: 'Complejo Uno', cuit: '30-11111111-9', razon_social: 'Pádel SA',
      estado: 'ok', detalle: '',
      identidad: { nombre: 'Pádel SA', cuit: '30-11111111-9', punto_venta: 1 },
      identidad_incompleta: false, cuit_discrepa: false,
      bloques: { nucleo: nucleo(100) },
    },
    {
      slug: 'c5', nombre: 'Complejo Cinco', cuit: '', razon_social: '',
      estado: 'sin_respuesta', detalle: 'ConnectTimeout: se apagó',
      identidad: { nombre: '', cuit: '', punto_venta: null },
      identidad_incompleta: false, cuit_discrepa: false,
      bloques: {},
    },
  ],
}

function montar() {
  return render(<MemoryRouter><Panel /></MemoryRouter>)
}

beforeEach(() => {
  resumenMock.mockReset()
  resumenMock.mockResolvedValue(CUATRO_DE_CINCO)
})

describe('el panel', () => {
  it('🔴 muestra el contador y el aviso de parcial, no sólo el número', async () => {
    montar()
    await waitFor(() => {
      expect(screen.getByTestId('contador-cobertura')).toHaveTextContent('4 de 5')
    })
    expect(screen.getByTestId('aviso-parcial')).toHaveTextContent('Complejo Cinco')
  })

  it('avisa que sumar entre CUITs no da una cifra declarable', async () => {
    montar()
    await waitFor(() => expect(screen.getByText(/número de\s*gestión/)).toBeInTheDocument())
  })

  it('muestra el período en dd-mm-aaaa', async () => {
    montar()
    await waitFor(() => {
      expect(screen.getByText('01-08-2026 al 20-08-2026')).toBeInTheDocument()
    })
  })

  it('le pide a la API el mes en curso, en ISO', async () => {
    montar()
    await waitFor(() => expect(resumenMock).toHaveBeenCalled())
    const [desde, hasta] = resumenMock.mock.calls[0]
    expect(desde).toMatch(/^\d{4}-\d{2}-01$/)
    expect(hasta).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('🔴 en la vista por razón social, la sucursal sin CUIT sale aparte y marcada', async () => {
    const usuario = userEvent.setup()
    montar()
    await waitFor(() => expect(screen.getByRole('tab', { name: /razón social/i })).toBeInTheDocument())
    await usuario.click(screen.getByRole('tab', { name: /razón social/i }))

    expect(screen.getByText('Pádel SA')).toBeInTheDocument()
    // No se junta con ninguna otra: aparece sola y con el motivo a la vista.
    expect(screen.getByTestId('sin-identificar')).toHaveTextContent('falta cargarle el CUIT')
  })

  it('en la vista por sucursal, la caída muestra el motivo y ningún número', async () => {
    const usuario = userEvent.setup()
    montar()
    await waitFor(() => expect(screen.getByRole('tab', { name: /sucursal/i })).toBeInTheDocument())
    await usuario.click(screen.getByRole('tab', { name: /Sucursal por sucursal/i }))

    const caida = screen.getByTestId('sucursal-c5')
    expect(caida).toHaveTextContent('Sin respuesta')
    expect(caida).toHaveTextContent('ConnectTimeout: se apagó')
    expect(caida).not.toHaveTextContent('$')
  })

  it('🔴 ante un error borra los datos viejos en vez de dejarlos en pantalla', async () => {
    const usuario = userEvent.setup()
    montar()
    await waitFor(() => expect(screen.getByTestId('contador-cobertura')).toBeInTheDocument())

    const { ApiError } = await import('../api')
    resumenMock.mockRejectedValue(new ApiError(500, 'se cayó todo'))
    await usuario.click(screen.getByRole('button', { name: /actualizar/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('se cayó todo'))
    // Dejar los números del pedido anterior es cómo se llega a que alguien lea
    // los del mes pasado creyendo que son los de hoy.
    expect(screen.queryByTestId('contador-cobertura')).toBeNull()
  })

  it('actualizar vuelve a preguntarle a las sucursales', async () => {
    const usuario = userEvent.setup()
    montar()
    await waitFor(() => expect(resumenMock).toHaveBeenCalledTimes(1))
    await usuario.click(screen.getByRole('button', { name: /actualizar/i }))
    await waitFor(() => expect(resumenMock).toHaveBeenCalledTimes(2))
  })
})
