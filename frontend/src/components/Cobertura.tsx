// El contador "N de M sucursales", que es la pieza que impide que el panel
// mienta.
//
// 🔴 **Va siempre, no sólo cuando falla alguna.** Un indicador que aparece
// únicamente ante un problema entrena a no mirarlo, y el día que aparece nadie
// lo lee. Cuando están todas dice "5 de 5" en gris; cuando falta alguna cambia
// de color, la nombra y dice por qué.
import { AlertTriangle, CheckCircle2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { Cobertura as CoberturaT } from '../api'

export function ContadorCobertura({ cobertura }: { cobertura: CoberturaT }) {
  const { respondieron, total, parcial } = cobertura
  const Icono = parcial ? AlertTriangle : CheckCircle2
  return (
    <Badge
      variant={parcial ? 'destructive' : 'secondary'}
      className="gap-1 whitespace-nowrap"
      data-testid="contador-cobertura"
    >
      <Icono className="size-3.5" />
      {respondieron} de {total} {total === 1 ? 'sucursal' : 'sucursales'}
    </Badge>
  )
}

/** El aviso que acompaña a un total parcial, con los nombres de las que faltan. */
export function AvisoParcial({ cobertura }: { cobertura: CoberturaT }) {
  if (!cobertura.parcial) return null
  return (
    <div
      role="alert"
      data-testid="aviso-parcial"
      className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
    >
      <p className="font-medium">
        Este total es parcial: falta{cobertura.sin_respuesta.length === 1 ? '' : 'n'}{' '}
        {cobertura.sin_respuesta.length} de {cobertura.total}{' '}
        {cobertura.total === 1 ? 'sucursal' : 'sucursales'}.
      </p>
      {/* La palabra que importa: una sucursal que no contesta NO vendió cero.
          Decirlo con todas las letras es más barato que que alguien tome una
          decisión sobre el número chico. */}
      <p className="mt-1 text-muted-foreground">
        Lo que falta no es cero: es desconocido. No se puede leer como el total
        del período.
      </p>
      <ul className="mt-2 space-y-1">
        {cobertura.sin_respuesta.map((s) => (
          <li key={s.slug}>
            <span className="font-medium">{s.nombre}</span>
            <span className="text-muted-foreground"> — {s.detalle}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
