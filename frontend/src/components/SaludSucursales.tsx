// El estado de cada sucursal: ¿contesta, y cuánto tarda?
//
// 🔴 **Dice si la sucursal está viva, no si sus números son buenos.** El
// `/health` es público, así que un «Responde» no prueba que la credencial del
// panel funcione: por eso una sucursal sin credencial lo avisa aparte en vez de
// quedar en verde a secas. Y si no contesta, se dice el motivo, no un «error».
//
// Va siempre que haya sucursales, no sólo cuando falla alguna (mismo criterio
// que el contador «N de M»): un indicador que sólo aparece ante un problema
// entrena a no mirarlo.
import { AlertTriangle, CheckCircle2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { Salud } from '../api'

export function SaludSucursales({ salud }: { salud: Salud }) {
  if (salud.sucursales.length === 0) return null
  const caidas = salud.sucursales.filter((s) => s.estado !== 'ok')
  return (
    <section aria-label="Estado de las sucursales" data-testid="salud-sucursales" className="space-y-2">
      <ul className="flex flex-wrap gap-2">
        {salud.sucursales.map((s) => {
          const ok = s.estado === 'ok'
          const Icono = ok ? CheckCircle2 : AlertTriangle
          return (
            <li key={s.slug} data-testid={`salud-${s.slug}`}>
              <Badge variant={ok ? 'secondary' : 'destructive'} className="gap-1 whitespace-nowrap">
                <Icono className="size-3.5" />
                {s.nombre}
                <span className="font-normal">
                  {ok ? 'responde' : 'sin respuesta'}
                  {s.latencia_ms !== null && ` · ${s.latencia_ms} ms`}
                  {s.version && ` · ${s.version}`}
                </span>
              </Badge>
              {ok && !s.tiene_credencial && (
                <Badge variant="outline" className="ml-1 whitespace-nowrap" data-testid={`sin-credencial-${s.slug}`}>
                  sin credencial
                </Badge>
              )}
            </li>
          )
        })}
      </ul>
      {caidas.length > 0 && (
        <ul className="space-y-1 text-sm text-muted-foreground" data-testid="salud-detalle">
          {caidas.map((s) => (
            <li key={s.slug}>
              <span className="font-medium text-foreground">{s.nombre}</span> — {s.detalle}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
