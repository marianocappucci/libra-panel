// Los bloques de números, con su propio denominador.
//
// 🔴 **Cada bloque dice de cuántas sucursales salió, y no siempre es el mismo
// número.** Una sucursal de MedLibra no mide ventas de buffet: el bloque de
// comercio sale de 3 sucursales aunque hayan contestado 5. Mostrar un solo
// "5 de 5" arriba de todo diría que el buffet también sale de cinco.
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Bloque } from '../api'
import { etiqueta, formatearValor, metricasDe } from '../lib/formato'

function LeyendaDelBloque({ bloque, respondieron }: { bloque: Bloque; respondieron: number }) {
  const propio = bloque.sucursales
  if (propio === respondieron) {
    return <span className="text-xs font-normal text-muted-foreground">de {propio}</span>
  }
  // El caso que hay que decir: este bloque salió de menos sucursales que las
  // que contestaron, porque las otras no lo miden.
  return (
    <span
      className="text-xs font-normal text-muted-foreground"
      title={`Lo reportan: ${bloque.slugs.join(', ')}. Las demás no miden esto.`}
      data-testid="leyenda-bloque-parcial"
    >
      de {propio} de {respondieron} que contestaron
    </span>
  )
}

export function TarjetasDeBloque({
  nombre, bloque, respondieron,
}: { nombre: string; bloque: Bloque; respondieron: number }) {
  const metricas = metricasDe(bloque.datos)
  return (
    <section className="space-y-3" data-testid={`bloque-${nombre}`}>
      <h3 className="flex items-baseline gap-2 text-sm font-semibold tracking-tight">
        {etiqueta(nombre)}
        <LeyendaDelBloque bloque={bloque} respondieron={respondieron} />
      </h3>
      {bloque.incompletos.length > 0 && (
        // Una clave que no estaba en todas las sucursales que sí mandaron el
        // bloque. Su total sale de menos lugares que el resto del bloque, y sin
        // decirlo parecería salir de todos.
        <p className="text-xs text-muted-foreground" data-testid="aviso-incompletos">
          Estos datos no los informan todas: {bloque.incompletos.map(etiqueta).join(', ')}.
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metricas.map((m) => (
          <Card key={m.ruta}>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                {m.etiqueta}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold tabular-nums">
                {formatearValor(m.clave, m.valor)}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  )
}

export function Consolidado({
  bloques, respondieron,
}: { bloques: Record<string, Bloque>; respondieron: number }) {
  const nombres = Object.keys(bloques)
  if (nombres.length === 0) {
    // 🔴 No se dibuja un consolidado en cero. Si ninguna sucursal contestó, no
    // hay de dónde sacar el número: un `$ 0` sería una invención perfectamente
    // creíble.
    return (
      <p className="text-sm text-muted-foreground" data-testid="sin-datos">
        Todavía no hay números para este período: ninguna sucursal contestó.
      </p>
    )
  }
  // `nucleo` primero: es lo único que tienen los seis productos.
  const orden = [...nombres].sort((a, b) => (a === 'nucleo' ? -1 : b === 'nucleo' ? 1 : a.localeCompare(b)))
  return (
    <div className="space-y-6">
      {orden.map((nombre) => (
        <TarjetasDeBloque
          key={nombre} nombre={nombre} bloque={bloques[nombre]} respondieron={respondieron}
        />
      ))}
    </div>
  )
}
