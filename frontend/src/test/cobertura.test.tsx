// Cómo se LEE un total parcial. Es lo propio del panel: la suma se prueba en
// el backend, y lo que se prueba acá es que la pantalla no deje pasar un
// número parcial como si fuera el total.
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Cobertura } from '../api'
import { AvisoParcial, ContadorCobertura } from '../components/Cobertura'

const COMPLETA: Cobertura = {
  total: 5, respondieron: 5, parcial: false, sin_respuesta: [],
}

const PARCIAL: Cobertura = {
  total: 5,
  respondieron: 4,
  parcial: true,
  sin_respuesta: [{ slug: 'c5', nombre: 'Complejo Cinco', detalle: 'ConnectTimeout' }],
}

describe('el contador de cobertura', () => {
  it('se muestra también cuando contestaron todas', () => {
    // 🔴 Un indicador que aparece sólo ante un problema entrena a no mirarlo, y
    // el día que aparece nadie lo lee.
    render(<ContadorCobertura cobertura={COMPLETA} />)
    expect(screen.getByTestId('contador-cobertura')).toHaveTextContent('5 de 5 sucursales')
  })

  it('dice cuántas contestaron cuando falta alguna', () => {
    render(<ContadorCobertura cobertura={PARCIAL} />)
    expect(screen.getByTestId('contador-cobertura')).toHaveTextContent('4 de 5 sucursales')
  })

  it('concuerda en singular con una sola sucursal', () => {
    render(<ContadorCobertura cobertura={{ ...COMPLETA, total: 1, respondieron: 1 }} />)
    expect(screen.getByTestId('contador-cobertura')).toHaveTextContent('1 de 1 sucursal')
  })
})

describe('el aviso de total parcial', () => {
  it('no aparece cuando contestaron todas', () => {
    render(<AvisoParcial cobertura={COMPLETA} />)
    expect(screen.queryByTestId('aviso-parcial')).toBeNull()
  })

  it('nombra las que faltan y dice por qué', () => {
    render(<AvisoParcial cobertura={PARCIAL} />)
    const aviso = screen.getByTestId('aviso-parcial')
    expect(aviso).toHaveTextContent('Complejo Cinco')
    expect(aviso).toHaveTextContent('ConnectTimeout')
  })

  it('dice con todas las letras que lo que falta no es cero', () => {
    // La frase es el punto del componente: sin ella, alguien lee el número
    // chico y toma una decisión sobre su negocio.
    render(<AvisoParcial cobertura={PARCIAL} />)
    expect(screen.getByTestId('aviso-parcial')).toHaveTextContent(
      'Lo que falta no es cero: es desconocido',
    )
  })

  it('es un role=alert, no un texto gris más', () => {
    render(<AvisoParcial cobertura={PARCIAL} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})
