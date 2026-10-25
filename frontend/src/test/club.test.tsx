// La vista de LibraClub: cinco filas de dos instancias, el mapa de calor y el origen.
//
// El criterio de aceptación del ROADMAP de LibraClub: «un dueño con dos
// instancias y cinco sucursales viendo cinco filas, no dos». Datos ficticios.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Club, ClubFila, Resumen } from '../api'
import { VistaClub } from '../components/Club'
import { etiquetaDeOrigen, formatearPorcentaje, formatearVariacion } from '../lib/formato'

function fila(
  slug: string, instancia: string, id: number, sucursal: string, extra: Partial<ClubFila> = {},
): ClubFila {
  return {
    slug, instancia, sucursal_id: id, sucursal,
    ocupacion_pct: 50, reservas: 100, horas_abiertas: null, horas_reservadas: null,
    canceladas: 2, ausentes: 1,
    ingresos: { reservas: 0, senas: 0, buffet: 0, total: 1000, total_periodo_anterior: 800 },
    variacion_pct: 25, origen: {}, franjas: [],
    ...extra,
  }
}

const CINCO: Club = {
  desde: '2026-10-01',
  hasta: '2026-10-24',
  periodo_uniforme: true,
  instancias: 2,
  slugs: ['norte', 'sur'],
  invalidos: [],
  por_sucursal: [
    fila('norte', 'Club Norte', 1, 'Centro', {
      ocupacion_pct: 60, reservas: 100, variacion_pct: 25,
      franjas: [{ dia: 0, hora: 18, ocupacion_pct: 90 }, { dia: 5, hora: 10, ocupacion_pct: 40 }],
    }),
    fila('norte', 'Club Norte', 2, 'Costanera', {
      ocupacion_pct: 80, reservas: 300, variacion_pct: -9.1,
      franjas: [{ dia: 0, hora: 18, ocupacion_pct: 70 }, { dia: 2, hora: 20, ocupacion_pct: 55 }],
    }),
    // El mismo `sucursal_id` 1 de otra instancia: el id es de cada base.
    fila('sur', 'Club Sur', 1, 'Centro', { ocupacion_pct: 50, variacion_pct: null }),
    fila('sur', 'Club Sur', 2, 'Puerto'),
    fila('sur', 'Club Sur', 3, 'Muelle'),
  ],
  totales: {
    sucursales: 5,
    ocupacion_pct: 66.5,
    criterio_ocupacion: 'ponderada_por_reservas',
    reservas: 800,
    canceladas: 22,
    ausentes: 10,
    ingresos: { reservas: null, senas: null, buffet: null, total: 7800, total_periodo_anterior: 6300 },
    variacion_pct: 23.8,
    origen: { mostrador: 50, portal: 70, whatsapp: 5, serie: 15, telefono: 5, qr_cancha: 5 },
  },
  franjas: [
    { dia: 0, hora: 18, ocupacion_pct: 80, sucursales: 2 },
    { dia: 2, hora: 20, ocupacion_pct: 55, sucursales: 1 },
    { dia: 5, hora: 10, ocupacion_pct: 40, sucursales: 1 },
  ],
}

describe('la tabla por sucursal', () => {
  it('🔴 dos instancias y cinco sucursales dan cinco filas, no dos', () => {
    render(<VistaClub club={CINCO} respondieron={2} />)

    const filas = screen.getAllByTestId('fila-club')
    expect(filas).toHaveLength(5)
    // Cada fila lleva el nombre de la instancia de donde viene.
    expect(within(filas[0]).getByText('Centro')).toBeInTheDocument()
    expect(within(filas[0]).getByText('Club Norte')).toBeInTheDocument()
    expect(within(filas[2]).getByText('Club Sur')).toBeInTheDocument()
  })

  it('suma el total general al pie y dice cuántas sucursales y de cuántas instancias', () => {
    render(<VistaClub club={CINCO} respondieron={2} />)

    const total = screen.getByTestId('fila-club-total')
    expect(total).toHaveTextContent('Total · 5 sucursales')
    expect(total).toHaveTextContent('2 instancias')
    expect(total).toHaveTextContent('66,5 %')
    expect(total).toHaveTextContent('800')
  })

  it('muestra la variación contra el período anterior con su signo, y «—» si no hay base', () => {
    render(<VistaClub club={CINCO} respondieron={2} />)

    const filas = screen.getAllByTestId('fila-club')
    expect(filas[0]).toHaveTextContent('+25,0 %')
    expect(filas[1]).toHaveTextContent('−9,1 %')
    // Sin período anterior no hay con qué comparar: ni +∞ ni 0 %.
    expect(within(filas[2]).getByTestId('variacion-sin-base')).toHaveTextContent('—')
  })

  it('🔴 un dato que no vino sale «—» y no 0', () => {
    const club: Club = {
      ...CINCO,
      por_sucursal: [fila('norte', 'Club Norte', 1, 'Centro', {
        ocupacion_pct: null, reservas: null, canceladas: null, ausentes: null,
        ingresos: { reservas: null, senas: null, buffet: null, total: null, total_periodo_anterior: null },
        variacion_pct: null,
      })],
    }
    render(<VistaClub club={club} respondieron={2} />)

    const celdas = within(screen.getByTestId('fila-club')).getAllByRole('cell')
    // Sucursal e instancia se leen; todo lo demás es «—».
    expect(celdas.slice(2).map((c) => c.textContent)).toEqual(['—', '—', '—', '—', '—', '—'])
  })
})

describe('los totales y su criterio', () => {
  it('muestra la ocupación general con el criterio escrito al lado', () => {
    render(<VistaClub club={CINCO} respondieron={2} />)

    const totales = screen.getByTestId('club-totales')
    expect(totales).toHaveTextContent('Ocupación general')
    expect(totales).toHaveTextContent('66,5 %')
    expect(totales).toHaveTextContent('ponderado por reservas')
    expect(screen.getByTestId('mapa-criterio')).toHaveTextContent('pondera por las reservas')
    expect(totales).toHaveTextContent('Contra el período anterior')
    expect(totales).toHaveTextContent('+23,8 %')
  })
})

describe('el criterio por horas', () => {
  const POR_HORAS: Club = {
    ...CINCO,
    totales: { ...CINCO.totales, ocupacion_pct: 60.8, criterio_ocupacion: 'ponderada_por_horas' },
  }

  it('dice que son horas reservadas sobre horas abiertas, en la tarjeta y en el mapa', () => {
    render(<VistaClub club={POR_HORAS} respondieron={2} />)

    const totales = screen.getByTestId('club-totales')
    expect(totales).toHaveTextContent('60,8 %')
    expect(totales).toHaveTextContent('Horas reservadas sobre horas abiertas')
    expect(totales).not.toHaveTextContent('ponderado por reservas')
    expect(screen.getByTestId('mapa-criterio')).toHaveTextContent('pondera por las horas abiertas')
  })
})

describe('los datos que no vinieron', () => {
  it('🔴 una sede sin base de LibraCore (ingresos null) y sin horas abiertas sale «—», no 0', () => {
    const sinBase = fila('norte', 'Club Norte', 9, 'Sin base', {
      ocupacion_pct: null, horas_abiertas: 0, horas_reservadas: 0,
      ingresos: { reservas: null, senas: null, buffet: null, total: null, total_periodo_anterior: null },
      variacion_pct: null,
    })
    const club: Club = {
      ...CINCO,
      por_sucursal: [sinBase],
      totales: {
        ...CINCO.totales, sucursales: 1, ocupacion_pct: null, variacion_pct: null,
        ingresos: { reservas: null, senas: null, buffet: null, total: null, total_periodo_anterior: null },
      },
    }
    render(<VistaClub club={club} respondieron={2} />)

    const celdas = within(screen.getByTestId('fila-club')).getAllByRole('cell')
    expect(celdas[2]).toHaveTextContent('—') // ocupación
    expect(celdas[6]).toHaveTextContent('—') // ingresos
    expect(celdas[7]).toHaveTextContent('—') // variación
    const totales = screen.getByTestId('club-totales')
    expect(totales).not.toHaveTextContent('$ 0')
    expect(totales).not.toHaveTextContent('0,0 %')
  })
})

describe('el período', () => {
  it('muestra el período que dijeron las instancias en club.desde / club.hasta', () => {
    render(<VistaClub club={CINCO} respondieron={2} />)
    expect(screen.getByTestId('club-periodo')).toHaveTextContent('01-10-2026 al 24-10-2026')
    expect(screen.queryByTestId('club-periodos-distintos')).toBeNull()
  })

  it('avisa si las instancias contestaron períodos distintos', () => {
    render(<VistaClub club={{ ...CINCO, desde: '2026-09-01', periodo_uniforme: false }} respondieron={2} />)
    expect(screen.getByTestId('club-periodos-distintos')).toHaveTextContent('períodos distintos')
  })

  it('sin período no inventa uno', () => {
    render(<VistaClub club={{ ...CINCO, desde: null, hasta: null }} respondieron={2} />)
    expect(screen.queryByTestId('club-periodo')).toBeNull()
  })
})

describe('el denominador', () => {
  it('no aclara nada cuando salió de todas las que contestaron', () => {
    render(<VistaClub club={CINCO} respondieron={2} />)
    expect(screen.queryByTestId('leyenda-club-parcial')).toBeNull()
    expect(screen.getByTestId('leyenda-club')).toHaveTextContent('de 2')
  })

  it('🔴 avisa cuando salió de menos instancias que las que contestaron', () => {
    // Una instancia vieja (o de otro producto) contesta sin `club`: no baja
    // ningún promedio, pero el número no sale de las tres.
    render(<VistaClub club={CINCO} respondieron={3} />)
    expect(screen.getByTestId('leyenda-club-parcial')).toHaveTextContent('de 2 de 3 que contestaron')
  })

  it('nombra la instancia que mandó datos ilegibles', () => {
    const club: Club = {
      ...CINCO,
      invalidos: [{ slug: 'rota', nombre: 'Club Roto', detalle: 'El bloque club no trae `por_sucursal` como lista.' }],
    }
    render(<VistaClub club={club} respondieron={3} />)
    expect(screen.getByTestId('club-invalidos')).toHaveTextContent('Club Roto')
    expect(screen.getByTestId('club-invalidos')).toHaveTextContent('no entran en estos números')
  })

  it('sin ninguna sucursal con datos no dibuja totales en cero', () => {
    const club: Club = { ...CINCO, por_sucursal: [], franjas: [] }
    render(<VistaClub club={club} respondieron={2} />)
    expect(screen.getByTestId('club-sin-sucursales')).toBeInTheDocument()
    expect(screen.queryByTestId('club-totales')).toBeNull()
    expect(screen.queryByTestId('club-tabla')).toBeNull()
  })
})

describe('el mapa de calor', () => {
  it('combinado: dibuja las franjas informadas y deja sin color las que no', () => {
    render(<VistaClub club={CINCO} respondieron={2} />)

    const mapa = screen.getByTestId('club-mapa')
    expect(within(mapa).getAllByTestId('celda-calor')).toHaveLength(3)
    // Horas de 10 a 20 (11 columnas) x 7 días = 77 celdas; 3 con dato.
    expect(within(mapa).getAllByTestId('celda-sin-dato')).toHaveLength(77 - 3)
    expect(within(mapa).getByTitle('lunes 18 h: 80,0 % (2 sucursales)')).toBeInTheDocument()
    expect(screen.getByTestId('mapa-extremos')).toHaveTextContent('Más ocupada: lunes 18 h (80,0 %)')
    expect(screen.getByTestId('mapa-extremos')).toHaveTextContent('Menos ocupada: sábado 10 h (40,0 %)')
  })

  it('por sucursal elegida: muestra sólo las franjas de esa sede', async () => {
    const user = userEvent.setup()
    render(<VistaClub club={CINCO} respondieron={2} />)

    await user.click(screen.getByRole('combobox', { name: 'Sucursal del mapa de calor' }))
    await user.click(await screen.findByRole('option', { name: /Costanera/ }))

    const mapa = screen.getByTestId('club-mapa')
    expect(within(mapa).getAllByTestId('celda-calor')).toHaveLength(2)
    expect(within(mapa).getByTitle('lunes 18 h: 70,0 %')).toBeInTheDocument()
    expect(screen.getByTestId('mapa-extremos')).toHaveTextContent('Más ocupada: lunes 18 h (70,0 %)')
  })

  it('una sucursal sin franjas lo dice en vez de dibujar una grilla en cero', async () => {
    const user = userEvent.setup()
    render(<VistaClub club={CINCO} respondieron={2} />)

    await user.click(screen.getByRole('combobox', { name: 'Sucursal del mapa de calor' }))
    await user.click(await screen.findByRole('option', { name: /Puerto/ }))

    expect(screen.getByTestId('mapa-vacio')).toBeInTheDocument()
    expect(screen.queryByTestId('mapa-calor')).toBeNull()
  })
})

describe('el origen de las reservas', () => {
  it('muestra la distribución, ordenada, con las claves que vengan', () => {
    render(<VistaClub club={CINCO} respondieron={2} />)

    const filas = screen.getAllByTestId('origen-fila')
    expect(filas).toHaveLength(6)
    // De mayor a menor.
    expect(filas[0]).toHaveTextContent('Portal web')
    expect(filas[0]).toHaveTextContent('70 · 46,7 %')
    expect(filas[1]).toHaveTextContent('Mostrador')
    // Una clave que no conoce se muestra prolija, no desaparece.
    expect(screen.getByText('Qr cancha')).toBeInTheDocument()
    expect(screen.getByText('Turno fijo (serie)')).toBeInTheDocument()
  })

  it('sin reservas con origen lo dice', () => {
    const club: Club = { ...CINCO, totales: { ...CINCO.totales, origen: {} } }
    render(<VistaClub club={club} respondieron={2} />)
    expect(screen.queryAllByTestId('origen-fila')).toHaveLength(0)
    expect(screen.getByTestId('club-origen')).toHaveTextContent('Sin reservas con origen informado')
  })
})

describe('el formato', () => {
  it('formatea porcentajes y variaciones, y no inventa ceros', () => {
    expect(formatearPorcentaje(66.5)).toBe('66,5 %')
    expect(formatearPorcentaje(null)).toBe('—')
    expect(formatearVariacion(23.8)).toBe('+23,8 %')
    expect(formatearVariacion(-9.1)).toBe('−9,1 %')
    expect(formatearVariacion(0)).toBe('0,0 %')
    expect(formatearVariacion(null)).toBe('—')
    expect(etiquetaDeOrigen('whatsapp')).toBe('WhatsApp')
  })
})

// ── La pantalla entera ──────────────────────────────────────────────────────

const resumenMock = vi.fn()
const saludMock = vi.fn()

vi.mock('../api', async (importOriginal) => {
  const real = await importOriginal<typeof import('../api')>()
  return { ...real, panel: { ...real.panel, resumen: resumenMock, salud: saludMock } }
})

const { Panel } = await import('../pages/Panel')

function resumen(club: Club | null | undefined): Resumen {
  return {
    periodo: { desde: '2026-10-01', hasta: '2026-10-24' },
    cobertura: { total: 3, respondieron: 3, parcial: false, sin_respuesta: [] },
    consolidado: {},
    ...(club === undefined ? {} : { club }),
    grupos: [],
    sucursales: [],
  }
}

describe('la pantalla del panel', () => {
  beforeEach(() => {
    resumenMock.mockReset()
    saludMock.mockReset()
    saludMock.mockResolvedValue({ total: 0, respondieron: 0, sucursales: [] })
  })

  it('con club suma la pestaña y muestra las cinco filas', async () => {
    resumenMock.mockResolvedValue(resumen(CINCO))
    const user = userEvent.setup()
    render(<MemoryRouter><Panel /></MemoryRouter>)

    await user.click(await screen.findByRole('tab', { name: 'Reservas y ocupación' }))

    await waitFor(() => expect(screen.getAllByTestId('fila-club')).toHaveLength(5))
    expect(screen.getByTestId('leyenda-club-parcial')).toHaveTextContent('de 2 de 3 que contestaron')
  })

  it('🔴 una respuesta sin club (instancia vieja) no rompe nada ni suma la pestaña', async () => {
    resumenMock.mockResolvedValue(resumen(undefined))
    render(<MemoryRouter><Panel /></MemoryRouter>)

    await screen.findByRole('tab', { name: 'Todas juntas' })
    expect(screen.queryByRole('tab', { name: 'Reservas y ocupación' })).toBeNull()
  })

  it('con club null tampoco hay pestaña', async () => {
    resumenMock.mockResolvedValue(resumen(null))
    render(<MemoryRouter><Panel /></MemoryRouter>)

    await screen.findByRole('tab', { name: 'Todas juntas' })
    expect(screen.queryByRole('tab', { name: 'Reservas y ocupación' })).toBeNull()
  })
})
