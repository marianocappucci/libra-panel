// El registro de sucursales.
//
// El test que importa acá es el de la credencial al editar: la pantalla nunca
// la recibe, así que si mandara siempre el campo del formulario mandaría vacío
// — y editarle el nombre a una sucursal le borraría la credencial, dejándola
// sin respuesta hasta que alguien mire.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Sucursal, Usuario } from '../api'

const mocks = {
  sucursales: vi.fn(),
  usuarios: vi.fn(),
  crearSucursal: vi.fn(),
  editarSucursal: vi.fn(),
  borrarSucursal: vi.fn(),
  asignar: vi.fn(),
  probar: vi.fn(),
}

vi.mock('../api', async (importOriginal) => {
  const real = await importOriginal<typeof import('../api')>()
  return { ...real, panel: { ...real.panel, ...mocks } }
})

const { Sucursales } = await import('../pages/Sucursales')

const UNA: Sucursal = {
  slug: 'c1', nombre: 'Complejo Uno', url_base: 'http://c1:8000',
  cuit: '30-11111111-9', razon_social: 'Pádel SA', activa: true,
  tiene_credencial: true, usuario_ids: [],
}

const USUARIOS: Usuario[] = [
  { id: '2', username: 'dueno', name: 'El dueño', role: 'socio', active: true },
]

beforeEach(() => {
  Object.values(mocks).forEach((m) => m.mockReset())
  mocks.sucursales.mockResolvedValue([UNA])
  mocks.usuarios.mockResolvedValue(USUARIOS)
  mocks.editarSucursal.mockResolvedValue(UNA)
  mocks.crearSucursal.mockResolvedValue(UNA)
  mocks.asignar.mockResolvedValue({ slug: 'c1', usuario_ids: [2] })
})

describe('el registro de sucursales', () => {
  it('🔴 editar sin tocar la credencial NO la manda', async () => {
    const usuario = userEvent.setup()
    render(<Sucursales />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await usuario.click(screen.getByRole('button', { name: /editar/i }))
    const nombre = await screen.findByLabelText('Nombre')
    await usuario.clear(nombre)
    await usuario.type(nombre, 'Complejo Uno bis')
    await usuario.click(screen.getByRole('button', { name: /guardar/i }))

    await waitFor(() => expect(mocks.editarSucursal).toHaveBeenCalled())
    const [, enviado] = mocks.editarSucursal.mock.calls[0]
    // Sin la clave: el backend distingue "no la mandó" de "la mandó vacía".
    expect(enviado).not.toHaveProperty('credencial')
    expect(enviado.nombre).toBe('Complejo Uno bis')
  })

  it('editar escribiendo una credencial sí la manda', async () => {
    const usuario = userEvent.setup()
    render(<Sucursales />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await usuario.click(screen.getByRole('button', { name: /editar/i }))
    await usuario.type(await screen.findByLabelText('Credencial de panel'), 'nueva-credencial')
    await usuario.click(screen.getByRole('button', { name: /guardar/i }))

    await waitFor(() => expect(mocks.editarSucursal).toHaveBeenCalled())
    expect(mocks.editarSucursal.mock.calls[0][1].credencial).toBe('nueva-credencial')
  })

  it('marca la sucursal sin credencial, que es un alta a medias', async () => {
    mocks.sucursales.mockResolvedValue([{ ...UNA, tiene_credencial: false }])
    render(<Sucursales />)
    await waitFor(() => expect(screen.getByText('Sin credencial')).toBeInTheDocument())
  })

  it('🔴 marca la sucursal sin CUIT: es la que no se puede agrupar', async () => {
    mocks.sucursales.mockResolvedValue([{ ...UNA, cuit: '', razon_social: '' }])
    render(<Sucursales />)
    await waitFor(() => {
      expect(screen.getByText(/no se agrupa por razón social/i)).toBeInTheDocument()
    })
  })

  it('probar dice qué bloques contesta y cómo se identifica', async () => {
    mocks.probar.mockResolvedValue({
      slug: 'c1', ok: true, detalle: '',
      identidad: { nombre: 'Pádel SA', cuit: '30-11111111-9', punto_venta: 1 },
      bloques: ['comercio', 'nucleo'],
    })
    const usuario = userEvent.setup()
    render(<Sucursales />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await usuario.click(screen.getByRole('button', { name: /probar/i }))
    const salida = await screen.findByTestId('prueba-c1')
    expect(salida).toHaveTextContent('comercio, nucleo')
    expect(salida).toHaveTextContent('30-11111111-9')
  })

  it('probar muestra el motivo cuando no contesta', async () => {
    mocks.probar.mockResolvedValue({ slug: 'c1', ok: false, detalle: 'HTTP 401: not authenticated' })
    const usuario = userEvent.setup()
    render(<Sucursales />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await usuario.click(screen.getByRole('button', { name: /probar/i }))
    expect(await screen.findByTestId('prueba-c1')).toHaveTextContent('HTTP 401')
  })

  it('el alta manda la credencial que se escribió', async () => {
    const usuario = userEvent.setup()
    render(<Sucursales />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await usuario.click(screen.getByRole('button', { name: /agregar/i }))
    await usuario.type(await screen.findByLabelText('Identificador'), 'c2')
    await usuario.type(screen.getByLabelText('Nombre'), 'Complejo Dos')
    await usuario.type(screen.getByLabelText('URL'), 'http://c2:8000')
    await usuario.type(screen.getByLabelText('Credencial de panel'), 'cred-c2')
    await usuario.click(screen.getByRole('button', { name: /guardar/i }))

    await waitFor(() => expect(mocks.crearSucursal).toHaveBeenCalled())
    expect(mocks.crearSucursal.mock.calls[0][0]).toMatchObject({
      slug: 'c2', url_base: 'http://c2:8000', credencial: 'cred-c2',
    })
  })

  it('asignar manda el conjunto completo de usuarios', async () => {
    const usuario = userEvent.setup()
    render(<Sucursales />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await usuario.click(screen.getByRole('checkbox'))
    await waitFor(() => expect(mocks.asignar).toHaveBeenCalledWith('c1', [2]))
  })
})
