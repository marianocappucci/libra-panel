// El cableado del captcha ALTCHA en las dos pantallas públicas.
//
// El recuadro en sí —el web component y su worker— lo prueba libra-ui; acá
// sólo lo único que es de este repo: que la sonda pegue a la ruta que monta
// `libra_panel/app.py` (`/auth/captcha`). Con otra, la sonda cae en el
// catch-all de la SPA, el recuadro no aparece y el backend rechaza cada login
// con un 400.
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { AuthProvider } from '../auth'

let fetchMock: ReturnType<typeof vi.fn>

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

/** Sin sesión: `/auth/me` responde 401, como con la cookie vencida.
 *
 *  La sonda del captcha contesta 404, no 401: el backend real la sirve sin
 *  sesión, y un 401 ahí lo tomaría el api-client de libra-ui por sesión
 *  vencida y recargaría en `/login`. */
beforeEach(() => {
  fetchMock = vi.fn((url: string) => {
    if (String(url) === '/auth/captcha') return Promise.resolve(json({ detail: 'Not Found' }, 404))
    return Promise.resolve(json({ detail: 'No autenticado' }, 401))
  })
  vi.stubGlobal('fetch', fetchMock)
})

function montar(ruta: string) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

function rutasPedidas() {
  return fetchMock.mock.calls.map((c) => String(c[0]))
}

describe('captcha', () => {
  it('el login pregunta por el captcha a /auth/captcha', async () => {
    montar('/login')
    await screen.findByRole('button', { name: /ingresar/i })
    await waitFor(() => expect(rutasPedidas()).toContain('/auth/captcha'))
  })

  it('«olvidé mi contraseña» también pregunta por el captcha', async () => {
    montar('/forgot-password')
    await waitFor(() => expect(rutasPedidas()).toContain('/auth/captcha'))
  })

  it('sin desafío (404) el login no dibuja el recuadro ni bloquea «Ingresar»', async () => {
    montar('/login')
    const boton = await screen.findByRole('button', { name: /ingresar/i })
    await waitFor(() => expect(rutasPedidas()).toContain('/auth/captcha'))
    expect(screen.queryByText(/no soy un robot/i)).toBeNull()
    expect(boton).not.toBeDisabled()
  })
})
