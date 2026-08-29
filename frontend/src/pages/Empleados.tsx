// El alta de un empleado en varias sucursales, desde un solo lugar.
//
// 🔑 **Sigue habiendo N usuarios, uno por sede, y eso es a propósito.** No es
// SSO: cada instancia mantiene su `libraauth` y su sesión. Lo que cambia es que
// se crean desde acá en vez de entrar a cada sistema. La contraseña también es
// una por sede — replicar un cambio de contraseña es replicar un secreto.
//
// 🔴 **El resultado nunca es un éxito liso.** Se muestra una fila por sucursal
// con lo que pasó en cada una. Una sede que no contesta no aborta el alta en
// las otras: el empleado empieza a trabajar en las que sí andan y la que falló
// se reintenta.
import { AlertCircle, Check, Loader2, MinusCircle } from 'lucide-react'
import { useEffect, useState } from 'react'

import type { AltaDeEmpleado, Sucursal } from '@/api'
import { panel } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const VACIO = { username: '', name: '', password: '', role: 'staff' }

/** El mínimo que exige el backend. Se repite acá para avisar antes de salir:
 *  una contraseña rechazada por la segunda sede dejaría al empleado creado en
 *  la primera y en ninguna otra. */
const LARGO_MINIMO = 8

function describir(err: unknown): string {
  const e = err as { body?: { detail?: unknown }; message?: string }
  const detalle = e?.body?.detail
  if (typeof detalle === 'string') return detalle
  return e?.message || 'No se pudo dar de alta.'
}

const ESTADOS = {
  creado: { texto: 'Creado', icono: Check, variant: 'default' as const },
  ya_estaba: { texto: 'Ya estaba', icono: MinusCircle, variant: 'secondary' as const },
  sin_respuesta: { texto: 'Sin respuesta', icono: AlertCircle, variant: 'destructive' as const },
}

export function Empleados() {
  const [sucursales, setSucursales] = useState<Sucursal[]>([])
  const [elegidas, setElegidas] = useState<string[]>([])
  const [form, setForm] = useState(VACIO)
  const [error, setError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<AltaDeEmpleado | null>(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    panel.sucursales()
      .then((s) => setSucursales(s.filter((x) => x.activa)))
      .catch((e) => setError(describir(e)))
  }, [])

  const sinCredencial = sucursales.filter((s) => !s.tiene_credencial)
  const cortaLaContrasena = form.password.length > 0 && form.password.length < LARGO_MINIMO
  const listo =
    form.username.trim() !== '' && form.name.trim() !== '' &&
    form.password.length >= LARGO_MINIMO && elegidas.length > 0

  function alternar(slug: string) {
    setElegidas((previas) =>
      previas.includes(slug) ? previas.filter((s) => s !== slug) : [...previas, slug],
    )
  }

  async function darDeAlta() {
    setEnviando(true)
    setError(null)
    setResultado(null)
    try {
      const r = await panel.altaDeEmpleado({ ...form, slugs: elegidas })
      setResultado(r)
      // La contraseña se limpia siempre; el resto queda por si hay que
      // reintentar en la sede que no contestó.
      setForm({ ...form, password: '' })
    } catch (e) {
      setError(describir(e))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Empleados</h1>
        <p className="text-sm text-muted-foreground">
          Da de alta un empleado en varias sucursales de una. Cada sede mantiene
          su propio usuario y su propia sesión: esto no es un inicio de sesión
          único, es una sola carga en vez de N.
        </p>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Datos del empleado</CardTitle>
          <CardDescription>
            Los mismos en todas las sucursales elegidas.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="username">Usuario</Label>
              <Input
                id="username" value={form.username} autoComplete="off"
                onChange={(e) => setForm({ ...form, username: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="name">Nombre</Label>
              <Input
                id="name" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password" type="password" value={form.password}
                autoComplete="new-password"
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                {cortaLaContrasena
                  ? `Mínimo ${LARGO_MINIMO} caracteres.`
                  : 'Viaja a cada sucursal y no se guarda en el panel.'}
              </p>
            </div>
            <div className="space-y-1">
              <Label htmlFor="role">Rol</Label>
              <Input
                id="role" value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                El vocabulario de roles es de cada producto: <code>staff</code>,
                <code> mostrador</code>, <code>admin</code>.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>En qué sucursales</CardTitle>
          <CardDescription>
            Sólo las activas. Ninguna viene marcada: dar de alta en todas por
            omisión es como se le crea un usuario en una sede donde no trabaja.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {sucursales.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No hay sucursales activas asignadas.
            </p>
          )}
          {sucursales.map((s) => (
            <label key={s.slug} className="flex items-center gap-3 text-sm">
              <Checkbox
                checked={elegidas.includes(s.slug)}
                disabled={!s.tiene_credencial}
                onCheckedChange={() => alternar(s.slug)}
                aria-label={s.nombre}
              />
              <span className={s.tiene_credencial ? '' : 'text-muted-foreground'}>
                {s.nombre}
              </span>
              <code className="text-xs text-muted-foreground">
                {s.url_base}{s.ruta_de_usuarios}
              </code>
              {!s.tiene_credencial && (
                <Badge variant="destructive">Sin credencial</Badge>
              )}
            </label>
          ))}
          {sinCredencial.length > 0 && (
            <p className="pt-2 text-xs text-muted-foreground">
              Las sucursales sin credencial no se pueden elegir: el panel entra
              con el <code>LIBRA_PANEL_TOKEN</code> de cada una. Se carga en
              Sucursales.
            </p>
          )}
        </CardContent>
      </Card>

      <Button disabled={!listo || enviando} onClick={() => void darDeAlta()}>
        {enviando && <Loader2 className="mr-2 size-4 animate-spin" />}
        Dar de alta
      </Button>

      {resultado && (
        <Card>
          <CardHeader>
            <CardTitle>
              {resultado.username}
              {resultado.parcial && (
                <Badge variant="destructive" className="ml-2">Parcial</Badge>
              )}
            </CardTitle>
            <CardDescription>
              {resultado.parcial
                ? 'Alguna sucursal no contestó. El empleado quedó dado de alta en las demás; reintentar sólo en las que fallaron.'
                : 'Quedó dado de alta en todas las sucursales elegidas.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {resultado.sucursales.map((f) => {
              const { texto, icono: Icono, variant } = ESTADOS[f.estado]
              return (
                <div key={f.slug} className="flex items-center gap-3 text-sm">
                  <Badge variant={variant}>
                    <Icono className="mr-1 size-3" />
                    {texto}
                  </Badge>
                  <span>{f.nombre}</span>
                  {f.estado === 'sin_respuesta' && (
                    <code className="text-xs text-muted-foreground">{f.detalle}</code>
                  )}
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
