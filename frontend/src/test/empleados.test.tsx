// La pantalla del alta de empleados.
//
// El test que importa acá es el del resultado parcial: el alta en varias sedes
// puede salir bien en unas y fallar en otras, y una pantalla que muestre un
// "listo" liso deja al dueño creyendo que el empleado puede entrar en todas.
// Es exactamente lo que hoy no puede saber cuando los crea a mano.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Sucursal } from '../api'

const mocks = {
  sucursales: vi.fn(),
  altaDeEmpleado: vi.fn(),
}

vi.mock('../api', async (importOriginal) => {
  const real = await importOriginal<typeof import('../api')>()
  return { ...real, panel: { ...real.panel, ...mocks } }
})

const { Empleados } = await import('../pages/Empleados')

function sucursal(over: Partial<Sucursal> = {}): Sucursal {
  return {
    slug: 'uno', nombre: 'Complejo Uno', url_base: 'http://uno:8000',
    cuit: '30-11111111-9', razon_social: 'Pádel SA', activa: true,
    tiene_credencial: true, ruta_de_usuarios: '/api/usuarios', usuario_ids: [],
    ...over,
  }
}

const DOS = [
  sucursal(),
  sucursal({ slug: 'dos', nombre: 'Complejo Dos', url_base: 'http://dos:8000' }),
]

beforeEach(() => {
  Object.values(mocks).forEach((m) => m.mockReset())
  mocks.sucursales.mockResolvedValue(DOS)
})

async function completar(usuario: ReturnType<typeof userEvent.setup>) {
  await usuario.type(screen.getByLabelText('Usuario'), 'sofia')
  await usuario.type(screen.getByLabelText('Nombre'), 'Sofía Díaz')
  await usuario.type(screen.getByLabelText('Contraseña'), 'una-contrasena-larga')
}

describe('el alta de un empleado', () => {
  it('🔴 el resultado parcial se ve sede por sede, no como un éxito liso', async () => {
    const usuario = userEvent.setup()
    mocks.altaDeEmpleado.mockResolvedValue({
      username: 'sofia', parcial: true,
      sucursales: [
        { slug: 'uno', nombre: 'Complejo Uno', estado: 'creado', detalle: 'sofia' },
        { slug: 'dos', nombre: 'Complejo Dos', estado: 'sin_respuesta', detalle: 'ConnectError: se cayó' },
      ],
    })
    render(<Empleados />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await completar(usuario)
    await usuario.click(screen.getByRole('checkbox', { name: 'Complejo Uno' }))
    await usuario.click(screen.getByRole('checkbox', { name: 'Complejo Dos' }))
    await usuario.click(screen.getByRole('button', { name: /dar de alta/i }))

    await waitFor(() => expect(screen.getByText('Parcial')).toBeInTheDocument())
    expect(screen.getByText('Creado')).toBeInTheDocument()
    expect(screen.getByText('Sin respuesta')).toBeInTheDocument()
    // El motivo de la que falló, para poder reintentar sólo esa.
    expect(screen.getByText(/ConnectError/)).toBeInTheDocument()
  })

  it('"ya estaba" no se muestra como una falla', async () => {
    const usuario = userEvent.setup()
    mocks.altaDeEmpleado.mockResolvedValue({
      username: 'sofia', parcial: false,
      sucursales: [
        { slug: 'uno', nombre: 'Complejo Uno', estado: 'ya_estaba', detalle: 'Ya existe.' },
        { slug: 'dos', nombre: 'Complejo Dos', estado: 'creado', detalle: 'sofia' },
      ],
    })
    render(<Empleados />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await completar(usuario)
    await usuario.click(screen.getByRole('checkbox', { name: 'Complejo Uno' }))
    await usuario.click(screen.getByRole('checkbox', { name: 'Complejo Dos' }))
    await usuario.click(screen.getByRole('button', { name: /dar de alta/i }))

    await waitFor(() => expect(screen.getByText('Ya estaba')).toBeInTheDocument())
    expect(screen.queryByText('Parcial')).not.toBeInTheDocument()
    expect(screen.queryByText('Sin respuesta')).not.toBeInTheDocument()
  })

  it('🔴 sin sucursal elegida no se puede dar de alta', async () => {
    const usuario = userEvent.setup()
    render(<Empleados />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await completar(usuario)

    // Ninguna viene marcada: dar de alta en todas por omisión es como se le
    // crea un usuario en una sede donde no trabaja.
    expect(screen.getByRole('button', { name: /dar de alta/i })).toBeDisabled()
    await usuario.click(screen.getByRole('checkbox', { name: 'Complejo Uno' }))
    expect(screen.getByRole('button', { name: /dar de alta/i })).toBeEnabled()
  })

  it('una contraseña corta no sale a ninguna sede', async () => {
    const usuario = userEvent.setup()
    render(<Empleados />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await usuario.type(screen.getByLabelText('Usuario'), 'sofia')
    await usuario.type(screen.getByLabelText('Nombre'), 'Sofía Díaz')
    await usuario.type(screen.getByLabelText('Contraseña'), 'corta')
    await usuario.click(screen.getByRole('checkbox', { name: 'Complejo Uno' }))

    expect(screen.getByRole('button', { name: /dar de alta/i })).toBeDisabled()
    expect(screen.getByText(/mínimo 8 caracteres/i)).toBeInTheDocument()
    // El que importa: rechazada por la segunda sede, dejaría al empleado
    // creado en la primera y en ninguna otra.
    expect(mocks.altaDeEmpleado).not.toHaveBeenCalled()
  })

  it('una sucursal sin credencial no se puede elegir', async () => {
    mocks.sucursales.mockResolvedValue([
      sucursal(),
      sucursal({ slug: 'dos', nombre: 'Complejo Dos', tiene_credencial: false }),
    ])
    render(<Empleados />)
    await waitFor(() => expect(screen.getByText('Complejo Dos')).toBeInTheDocument())

    // El panel entra con el LIBRA_PANEL_TOKEN de cada sede: sin credencial no
    // hay con qué. Deshabilitada y no escondida, para que se vea por qué.
    expect(screen.getByRole('checkbox', { name: 'Complejo Dos' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Complejo Uno' })).toBeEnabled()
  })

  it('una sucursal inactiva no aparece', async () => {
    mocks.sucursales.mockResolvedValue([
      sucursal(),
      sucursal({ slug: 'dos', nombre: 'Complejo Dos', activa: false }),
    ])
    render(<Empleados />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    expect(screen.queryByText('Complejo Dos')).not.toBeInTheDocument()
  })

  it('se manda lo elegido y nada más', async () => {
    const usuario = userEvent.setup()
    mocks.altaDeEmpleado.mockResolvedValue({
      username: 'sofia', parcial: false,
      sucursales: [{ slug: 'dos', nombre: 'Complejo Dos', estado: 'creado', detalle: 'sofia' }],
    })
    render(<Empleados />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await completar(usuario)
    await usuario.click(screen.getByRole('checkbox', { name: 'Complejo Dos' }))
    await usuario.click(screen.getByRole('button', { name: /dar de alta/i }))

    await waitFor(() => expect(mocks.altaDeEmpleado).toHaveBeenCalled())
    expect(mocks.altaDeEmpleado.mock.calls[0][0]).toEqual({
      username: 'sofia', name: 'Sofía Díaz',
      password: 'una-contrasena-larga', role: 'staff', slugs: ['dos'],
    })
  })

  it('la ruta de cada sucursal se ve, porque no es la misma en todos', async () => {
    mocks.sucursales.mockResolvedValue([
      sucursal(),
      sucursal({
        slug: 'dos', nombre: 'Complejo Dos', url_base: 'http://dos:8000',
        ruta_de_usuarios: '/users',
      }),
    ])
    render(<Empleados />)

    // Sin esto no hay forma de notar que una sucursal quedó cargada con la
    // ruta del producto equivocado hasta que el alta falla.
    await waitFor(() =>
      expect(screen.getByText('http://dos:8000/users')).toBeInTheDocument(),
    )
    expect(screen.getByText('http://uno:8000/api/usuarios')).toBeInTheDocument()
  })

  it('un error del backend se muestra y no se pierde', async () => {
    const usuario = userEvent.setup()
    mocks.altaDeEmpleado.mockRejectedValue({
      body: { detail: 'Estas sucursales no existen o no las tenes asignadas.' },
    })
    render(<Empleados />)
    await waitFor(() => expect(screen.getByText('Complejo Uno')).toBeInTheDocument())

    await completar(usuario)
    await usuario.click(screen.getByRole('checkbox', { name: 'Complejo Uno' }))
    await usuario.click(screen.getByRole('button', { name: /dar de alta/i }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/no las tenes asignadas/),
    )
  })
})
