// La vista de LibraClub: el panel del dueño con varias instancias y varias sedes.
//
// El criterio de aceptación del ROADMAP de LibraClub: «un dueño con dos
// instancias y cinco sucursales viendo cinco filas, no dos». La tabla sale por
// sucursal **del club**; la instancia sólo aparece como columna.
//
// 🔴 Tres cosas que esta pantalla no hace, porque son las que harían mentir al
// panel (las mismas reglas que `Bloques.tsx`):
//   - Un dato que no vino (`null`) sale «—», nunca `0`. Cero es «no hubo».
//   - El denominador va siempre: «de 2 de 3 que contestaron». Una instancia sin
//     el bloque `club` (vieja, o de otro producto) no baja ningún promedio.
//   - La ocupación general lleva su criterio al lado (ponderada por reservas),
//     porque un porcentaje promediado a ciegas es otro número.
import { useMemo, useState, type ReactNode } from 'react'
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { SelectBuscable } from 'libra-ui/SelectBuscable'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import type { Club, ClubFila, ClubFranja } from '../api'
import {
  DIAS_CORTOS, DIAS_LARGOS, etiquetaDeOrigen, formatearConteo, formatearPlata,
  formatearPorcentaje, formatearVariacion,
} from '../lib/formato'

// ── Piezas chicas ───────────────────────────────────────────────────────────

/** La variación contra el período anterior. Sin base de comparación, «—». */
function Variacion({ valor }: { valor: number | null }) {
  if (valor === null || valor === undefined) {
    return (
      <span
        className="text-muted-foreground"
        title="Sin período anterior con qué comparar."
        data-testid="variacion-sin-base"
      >
        —
      </span>
    )
  }
  // Sin verde: el color de "bien" no se lee igual en los dos modos ni para todos
  // los ojos. La flecha y el signo ya dicen el sentido; el rojo (token
  // `destructive`) se reserva para lo que cae.
  const Icono = valor > 0 ? ArrowUpRight : valor < 0 ? ArrowDownRight : Minus
  return (
    <span
      className={`inline-flex items-center gap-1 tabular-nums ${valor < 0 ? 'text-destructive' : ''}`}
    >
      <Icono className="size-3.5" aria-hidden />
      {formatearVariacion(valor)}
    </span>
  )
}

function Leyenda({ club, respondieron }: { club: Club; respondieron: number }) {
  const propio = club.instancias
  const iguales = propio === respondieron
  return (
    <span
      className="text-xs font-normal text-muted-foreground"
      title={iguales ? undefined : `Lo informan: ${club.slugs.join(', ')}. Las demás no lo miden.`}
      data-testid={iguales ? 'leyenda-club' : 'leyenda-club-parcial'}
    >
      {iguales ? `de ${propio}` : `de ${propio} de ${respondieron} que contestaron`}
    </span>
  )
}

function Cifra({
  titulo, valor, nota, children,
}: { titulo: string; valor: string; nota?: string; children?: ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium text-muted-foreground">{titulo}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <p className="text-2xl font-semibold tabular-nums">{valor}</p>
        {children}
        {nota && <p className="text-xs text-muted-foreground">{nota}</p>}
      </CardContent>
    </Card>
  )
}

// ── Totales ─────────────────────────────────────────────────────────────────

function Totales({ club }: { club: Club }) {
  const t = club.totales
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="club-totales">
      <Cifra
        titulo="Ocupación general"
        valor={formatearPorcentaje(t.ocupacion_pct)}
        // El criterio, escrito: un porcentaje no se suma ni se promedia sin decir cómo.
        nota={
          t.criterio_ocupacion === 'ponderada_por_reservas'
            ? 'Promedio ponderado por reservas de cada sucursal.'
            : undefined
        }
      />
      <Cifra titulo="Reservas" valor={formatearConteo(t.reservas)} />
      <Cifra titulo="Canceladas" valor={formatearConteo(t.canceladas)} />
      <Cifra titulo="Ausentes" valor={formatearConteo(t.ausentes)} />
      <Cifra titulo="Ingresos" valor={formatearPlata(t.ingresos.total)}>
        <p className="text-xs text-muted-foreground">
          Contra el período anterior: <Variacion valor={t.variacion_pct} />
        </p>
      </Cifra>
    </div>
  )
}

// ── Tabla: una fila por sucursal del club ───────────────────────────────────

function TablaPorSucursal({ club }: { club: Club }) {
  const t = club.totales
  const varias = new Set(club.por_sucursal.map((f) => f.slug)).size > 1
  return (
    <section className="space-y-3" data-testid="club-tabla">
      <h3 className="text-sm font-semibold tracking-tight">Por sucursal</h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Sucursal</TableHead>
            <TableHead>Instancia</TableHead>
            <TableHead className="text-right">Ocupación</TableHead>
            <TableHead className="text-right">Reservas</TableHead>
            <TableHead className="text-right">Canceladas</TableHead>
            <TableHead className="text-right">Ausentes</TableHead>
            <TableHead className="text-right">Ingresos</TableHead>
            <TableHead className="text-right">Vs. período anterior</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {club.por_sucursal.map((f, i) => (
            <TableRow key={`${f.slug}:${f.sucursal_id}:${i}`} data-testid="fila-club">
              <TableCell className="font-medium">{f.sucursal || '—'}</TableCell>
              <TableCell className="text-muted-foreground">{f.instancia}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatearPorcentaje(f.ocupacion_pct)}
              </TableCell>
              <TableCell className="text-right tabular-nums">{formatearConteo(f.reservas)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatearConteo(f.canceladas)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatearConteo(f.ausentes)}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatearPlata(f.ingresos.total)}
              </TableCell>
              <TableCell className="text-right">
                <Variacion valor={f.variacion_pct} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
        {club.por_sucursal.length > 0 && (
          <TableFooter>
            <TableRow data-testid="fila-club-total">
              <TableCell className="font-semibold">
                Total · {t.sucursales} {t.sucursales === 1 ? 'sucursal' : 'sucursales'}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {varias ? `${club.instancias} instancias` : ''}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatearPorcentaje(t.ocupacion_pct)}
              </TableCell>
              <TableCell className="text-right tabular-nums">{formatearConteo(t.reservas)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatearConteo(t.canceladas)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatearConteo(t.ausentes)}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatearPlata(t.ingresos.total)}
              </TableCell>
              <TableCell className="text-right">
                <Variacion valor={t.variacion_pct} />
              </TableCell>
            </TableRow>
          </TableFooter>
        )}
      </Table>
    </section>
  )
}

// ── Mapa de calor día × hora ────────────────────────────────────────────────

const TODAS = ''

function valorDeFila(f: ClubFila, i: number): string {
  return `${f.slug}:${f.sucursal_id}:${i}`
}

/** El color de una celda: el `primary` del tema con más cuerpo cuanto más ocupada.
 *  Sale de un token y no de un color fijo, así que sigue al modo oscuro. */
function fondoDeCelda(pct: number): string {
  const intensidad = Math.max(0, Math.min(100, pct))
  return `color-mix(in oklab, var(--primary) ${Math.round(8 + intensidad * 0.82)}%, transparent)`
}

function MapaDeCalor({ franjas }: { franjas: ClubFranja[] }) {
  const validas = franjas.filter((f) => f.ocupacion_pct !== null)
  if (validas.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="mapa-vacio">
        No hay franjas horarias informadas para este período.
      </p>
    )
  }
  const celdas = new Map(validas.map((f) => [`${f.dia}:${f.hora}`, f]))
  const horaMin = Math.min(...validas.map((f) => f.hora))
  const horaMax = Math.max(...validas.map((f) => f.hora))
  const horas = Array.from({ length: horaMax - horaMin + 1 }, (_, i) => horaMin + i)

  const orden = [...validas].sort((a, b) => (b.ocupacion_pct ?? 0) - (a.ocupacion_pct ?? 0))
  const mas = orden[0]
  const menos = orden[orden.length - 1]
  const nombre = (f: ClubFranja) => `${DIAS_LARGOS[f.dia]} ${f.hora} h (${formatearPorcentaje(f.ocupacion_pct)})`

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] border-separate border-spacing-0.5 text-xs" data-testid="mapa-calor">
          <thead>
            <tr>
              <th scope="col" className="w-10" />
              {horas.map((h) => (
                <th key={h} scope="col" className="font-normal tabular-nums text-muted-foreground">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {DIAS_CORTOS.map((dia, d) => (
              <tr key={dia}>
                <th scope="row" className="pr-2 text-left font-normal text-muted-foreground">{dia}</th>
                {horas.map((h) => {
                  const f = celdas.get(`${d}:${h}`)
                  if (!f || f.ocupacion_pct === null) {
                    // Sin dato no es 0 %: la celda queda vacía, sin color.
                    return (
                      <td
                        key={h}
                        className="h-6 rounded-sm border border-dashed border-border"
                        data-testid="celda-sin-dato"
                        title={`${DIAS_LARGOS[d]} ${h} h: sin dato`}
                      />
                    )
                  }
                  return (
                    <td
                      key={h}
                      className="h-6 rounded-sm"
                      style={{ backgroundColor: fondoDeCelda(f.ocupacion_pct) }}
                      data-testid="celda-calor"
                      title={
                        `${DIAS_LARGOS[d]} ${h} h: ${formatearPorcentaje(f.ocupacion_pct)}` +
                        (f.sucursales ? ` (${f.sucursales} ${f.sucursales === 1 ? 'sucursal' : 'sucursales'})` : '')
                      }
                    >
                      <span className="sr-only">
                        {DIAS_LARGOS[d]} {h} h: {formatearPorcentaje(f.ocupacion_pct)}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-2" aria-hidden>
          0 %
          <span
            className="h-2 w-24 rounded-sm"
            style={{ background: 'linear-gradient(to right, color-mix(in oklab, var(--primary) 8%, transparent), var(--primary))' }}
          />
          100 %
        </span>
        <span data-testid="mapa-extremos">
          Más ocupada: {nombre(mas)}
          {menos !== mas && <> · Menos ocupada: {nombre(menos)}</>}
        </span>
      </div>
    </div>
  )
}

function SeccionMapa({ club }: { club: Club }) {
  const [elegida, setElegida] = useState(TODAS)
  const opciones = useMemo(
    () => [
      { value: TODAS, label: 'Todas, combinadas' },
      ...club.por_sucursal.map((f, i) => ({
        value: valorDeFila(f, i),
        label: `${f.sucursal || 'Sin nombre'} · ${f.instancia}`,
      })),
    ],
    [club.por_sucursal],
  )
  const fila = club.por_sucursal.find((f, i) => valorDeFila(f, i) === elegida)
  const franjas = fila ? fila.franjas : club.franjas

  return (
    <section className="space-y-3" data-testid="club-mapa">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">Ocupación por día y hora</h3>
          {!fila && (
            <p className="text-xs text-muted-foreground">
              Combinado: cada franja pondera por las reservas de las sucursales que la informan.
            </p>
          )}
        </div>
        <SelectBuscable
          value={elegida}
          onChange={setElegida}
          opciones={opciones}
          ariaLabel="Sucursal del mapa de calor"
          placeholder="Buscar sucursal…"
          className="w-64"
        />
      </div>
      <MapaDeCalor franjas={franjas} />
    </section>
  )
}

// ── Origen de las reservas ──────────────────────────────────────────────────

function Origen({ origen }: { origen: Record<string, number> }) {
  const filas = Object.entries(origen).sort((a, b) => b[1] - a[1])
  const total = filas.reduce((acc, [, n]) => acc + n, 0)
  return (
    <section className="space-y-3" data-testid="club-origen">
      <h3 className="text-sm font-semibold tracking-tight">Origen de las reservas</h3>
      {total <= 0 ? (
        <p className="text-sm text-muted-foreground">Sin reservas con origen informado en este período.</p>
      ) : (
        <ul className="space-y-2">
          {filas.map(([clave, cantidad]) => {
            const pct = (cantidad / total) * 100
            return (
              <li key={clave} className="grid grid-cols-[8rem_1fr_6rem] items-center gap-3 text-sm" data-testid="origen-fila">
                <span>{etiquetaDeOrigen(clave)}</span>
                <span className="h-2 rounded-sm bg-muted" aria-hidden>
                  <span className="block h-full rounded-sm bg-primary" style={{ width: `${pct}%` }} />
                </span>
                <span className="text-right tabular-nums text-muted-foreground">
                  {formatearConteo(cantidad)} · {formatearPorcentaje(pct)}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

// ── La vista ────────────────────────────────────────────────────────────────

export function VistaClub({ club, respondieron }: { club: Club; respondieron: number }) {
  return (
    <div className="space-y-8" data-testid="vista-club">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Reservas y ocupación</h2>
        <Leyenda club={club} respondieron={respondieron} />
      </div>

      {club.invalidos.length > 0 && (
        // Una instancia mandó `club` con una forma que no se puede leer. Se
        // nombra: callarla dejaría un total que parece completo y no lo es.
        <div role="alert" data-testid="club-invalidos" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          <p className="font-medium">
            {club.invalidos.length === 1 ? 'Una instancia mandó' : `${club.invalidos.length} instancias mandaron`} datos de
            club que no se pueden leer, y no entran en estos números.
          </p>
          <ul className="mt-1 space-y-1">
            {club.invalidos.map((i) => (
              <li key={i.slug}>
                <span className="font-medium">{i.nombre}</span>
                <span className="text-muted-foreground"> — {i.detalle}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {club.por_sucursal.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="club-sin-sucursales">
          Todavía no hay sucursales con datos para este período.
        </p>
      ) : (
        <>
          <Totales club={club} />
          <TablaPorSucursal club={club} />
          <SeccionMapa club={club} />
          <Origen origen={club.totales.origen} />
        </>
      )}
    </div>
  )
}
