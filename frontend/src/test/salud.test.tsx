// El estado de cada sucursal: el componente y su lugar en la pantalla.
//
// Lo que se cuida: que una sucursal caída se vea CAÍDA y con su motivo, que un
// «responde» no se lea como «sus números van a venir» (sin credencial), y que el
// estado y el resumen no se tumben entre sí.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Resumen, Salud } from '../api'

const resumenMock = vi.fn()
const saludMock = vi.fn()

vi.mock('../api', async (importOriginal) => {
  const real = await importOriginal<typeof import('../api')>()
  return { ...real, panel: { ...real.panel, resumen: resumenMock, salud: saludMock } }
})

// `ApiError` se importa DESPUÉS del mock: un import estático de '../api' se evalúa antes
// que `resumenMock` y el `vi.mock` de arriba revienta por usarlo sin inicializar.
const { ApiError } = await import('../api')
const { Panel } = await import('../pages/Panel')
const { SaludSucursales } = await import('../components/SaludSucursales')

const SALUD: Salud = {
  total: 3,
  respondieron: 2,
  sucursales: [
    { slug: 'c1', nombre: 'Complejo Uno', estado: 'ok', latencia_ms: 42, version: null, detalle: '', tiene_credencial: true },
    {
      slug: 'c2', nombre: 'Complejo Dos', estado: 'ok', latencia_ms: 130, version: 'v2026.10.12-103000',
      detalle: '', tiene_credencial: false,
    },
    {
      slug: 'c3', nombre: 'Complejo Tres', estado: 'sin_respuesta', latencia_ms: 3001, version: null,
      detalle: 'No contestó el /health en 3 s.', tiene_credencial: true,
    },
  ],
}

const RESUMEN_VACIO: Resumen = {
  periodo: { desde: '2026-10-01', hasta: '2026-10-15' },
  cobertura: { total: 0, respondieron: 0, parcial: false, sin_respuesta: [] },
  consolidado: {},
  grupos: [],
  sucursales: [],
}

describe('SaludSucursales', () => {
  it('muestra una fila por sucursal con su latencia', () => {
    render(<SaludSucursales salud={SALUD} />)

    const uno = screen.getByTestId('salud-c1')
    expect(within(uno).getByText('Complejo Uno')).toBeInTheDocument()
    expect(uno).toHaveTextContent('responde · 42 ms')
    expect(screen.getAllByRole('listitem').filter((li) => li.dataset.testid?.startsWith('salud-c'))).toHaveLength(3)
  })

  it('🔴 una sucursal caída figura sin respuesta y con su motivo, no «error»', () => {
    render(<SaludSucursales salud={SALUD} />)

    expect(screen.getByTestId('salud-c3')).toHaveTextContent('sin respuesta · 3001 ms')
    expect(screen.getByTestId('salud-detalle')).toHaveTextContent('Complejo Tres — No contestó el /health en 3 s.')
  })

  it('con todas arriba no dibuja el detalle de caídas (control positivo)', () => {
    render(<SaludSucursales salud={{ ...SALUD, sucursales: SALUD.sucursales.slice(0, 2) }} />)
    expect(screen.queryByTestId('salud-detalle')).not.toBeInTheDocument()
    expect(screen.queryByText(/sin respuesta/)).not.toBeInTheDocument()
  })

  it('🔴 «responde» sin credencial lo avisa: el verde no promete números', () => {
    render(<SaludSucursales salud={SALUD} />)

    expect(screen.getByTestId('sin-credencial-c2')).toBeInTheDocument()
    expect(screen.queryByTestId('sin-credencial-c1')).not.toBeInTheDocument()
  })

  it('la versión aparece sólo si la instancia la manda', () => {
    render(<SaludSucursales salud={SALUD} />)

    expect(screen.getByTestId('salud-c2')).toHaveTextContent('v2026.10.12-103000')
    expect(screen.getByTestId('salud-c1')).not.toHaveTextContent(/v20\d\d/)
  })

  it('sin sucursales no dibuja nada', () => {
    const { container } = render(<SaludSucursales salud={{ total: 0, respondieron: 0, sucursales: [] }} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('el estado en la pantalla principal', () => {
  beforeEach(() => {
    resumenMock.mockReset()
    resumenMock.mockResolvedValue(RESUMEN_VACIO)
    saludMock.mockReset()
    saludMock.mockResolvedValue(SALUD)
  })

  const montar = () => render(<MemoryRouter><Panel /></MemoryRouter>)

  it('se pide al abrir y se dibuja junto al resumen', async () => {
    montar()

    expect(await screen.findByTestId('salud-sucursales')).toBeInTheDocument()
    expect(saludMock).toHaveBeenCalledTimes(1)
    expect(resumenMock).toHaveBeenCalledTimes(1)
  })

  it('«Actualizar» vuelve a preguntar el estado, no sólo el resumen', async () => {
    montar()
    await screen.findByTestId('salud-sucursales')
    await waitFor(() => expect(screen.getByRole('button', { name: /actualizar/i })).toBeEnabled())

    await userEvent.click(screen.getByRole('button', { name: /actualizar/i }))

    await waitFor(() => expect(saludMock).toHaveBeenCalledTimes(2))
    expect(resumenMock).toHaveBeenCalledTimes(2)
  })

  it('🔴 si falla el estado, el resumen se ve igual y el fallo se dice', async () => {
    saludMock.mockRejectedValue(new ApiError(500, 'boom'))
    montar()

    expect(await screen.findByTestId('salud-error')).toHaveTextContent('No se pudo consultar el estado')
    expect(screen.queryByTestId('salud-sucursales')).not.toBeInTheDocument()
    // El resumen sigue: su cobertura está en pantalla.
    expect(await screen.findByTestId('contador-cobertura')).toBeInTheDocument()
  })

  it('🔴 si falla el resumen, el estado se ve igual (es justo cuando más sirve)', async () => {
    resumenMock.mockRejectedValue(new ApiError(502, 'las sucursales no contestan'))
    montar()

    expect(await screen.findByRole('alert')).toHaveTextContent('las sucursales no contestan')
    expect(await screen.findByTestId('salud-sucursales')).toBeInTheDocument()
  })

  it('un error del estado no deja pegado lo viejo: «Actualizar» lo borra', async () => {
    montar()
    await screen.findByTestId('salud-sucursales')
    saludMock.mockRejectedValue(new ApiError(500, 'boom'))
    await waitFor(() => expect(screen.getByRole('button', { name: /actualizar/i })).toBeEnabled())

    await userEvent.click(screen.getByRole('button', { name: /actualizar/i }))

    await waitFor(() => expect(screen.queryByTestId('salud-sucursales')).not.toBeInTheDocument())
    expect(screen.getByTestId('salud-error')).toBeInTheDocument()
  })
})
