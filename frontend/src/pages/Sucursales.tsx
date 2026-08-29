// El registro de sucursales. **Sólo lo ve un admin** (o sea, nosotros).
//
// El panel es de sólo lectura hacia las sucursales: acá no se le escribe nada
// a ninguna. Lo que se administra es el registro propio del panel — qué
// sucursal existe, en qué URL, con qué credencial y quién la ve.
import { useEffect, useState } from 'react'
import { Plug, Plus, Trash2, Pencil } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import { ApiError, panel, type PruebaSucursal, type Sucursal, type Usuario } from '../api'

const VACIA = {
  slug: '', nombre: '', url_base: '', cuit: '', razon_social: '',
  credencial: '', ruta_de_usuarios: '/api/usuarios', activa: true,
}

function describir(err: unknown): string {
  return err instanceof ApiError ? err.detail : 'Error de conexión.'
}

export function Sucursales() {
  const [filas, setFilas] = useState<Sucursal[]>([])
  const [usuarios, setUsuarios] = useState<Usuario[]>([])
  const [error, setError] = useState<string | null>(null)
  const [editando, setEditando] = useState<string | null>(null)
  const [form, setForm] = useState(VACIA)
  const [pruebas, setPruebas] = useState<Record<string, PruebaSucursal>>({})

  useEffect(() => {
    void cargar()
  }, [])

  async function cargar() {
    try {
      const [s, u] = await Promise.all([panel.sucursales(), panel.usuarios()])
      setFilas(s)
      setUsuarios(u)
    } catch (err) {
      setError(describir(err))
    }
  }

  function empezarAlta() {
    setForm(VACIA)
    setEditando('nueva')
  }

  function empezarEdicion(s: Sucursal) {
    // 🔴 La credencial arranca VACÍA y eso significa "no la toques".
    // La pantalla nunca la recibe —el backend no la devuelve—, así que si el
    // formulario la mandara siempre, editar el nombre de una sucursal le
    // borraría la credencial.
    setForm({ ...s, credencial: '' })
    setEditando(s.slug)
  }

  async function guardar() {
    setError(null)
    try {
      if (editando === 'nueva') {
        await panel.crearSucursal(form)
      } else if (editando) {
        const { credencial, ...resto } = form
        await panel.editarSucursal(editando, credencial ? form : resto)
      }
      setEditando(null)
      await cargar()
    } catch (err) {
      setError(describir(err))
    }
  }

  async function borrar(slug: string) {
    if (!confirm(`¿Sacar la sucursal "${slug}" del panel?`)) return
    try {
      await panel.borrarSucursal(slug)
      await cargar()
    } catch (err) {
      setError(describir(err))
    }
  }

  async function probar(slug: string) {
    try {
      const resultado = await panel.probar(slug)
      setPruebas((p) => ({ ...p, [slug]: resultado }))
    } catch (err) {
      setPruebas((p) => ({ ...p, [slug]: { slug, ok: false, detalle: describir(err) } }))
    }
  }

  async function guardarParticipacion(s: Sucursal, usuarioId: number, valor: string) {
    const numero = Number(valor)
    // Un campo vacío o con letras no se manda: el backend lo rechazaría con un
    // 422 y el operador vería un error por haber borrado el contenido para
    // reescribirlo.
    if (valor.trim() === '' || Number.isNaN(numero)) return
    if (numero === (s.participaciones?.[String(usuarioId)] ?? 0)) return
    try {
      await panel.participacion(s.slug, usuarioId, numero)
      await cargar()
    } catch (err) {
      setError(describir(err))
    }
  }

  async function alternarUsuario(s: Sucursal, usuarioId: number) {
    const actuales = s.usuario_ids ?? []
    const nuevos = actuales.includes(usuarioId)
      ? actuales.filter((u) => u !== usuarioId)
      : [...actuales, usuarioId]
    try {
      await panel.asignar(s.slug, nuevos)
      await cargar()
    } catch (err) {
      setError(describir(err))
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sucursales</h1>
          <p className="text-sm text-muted-foreground">
            El registro del panel. Cada sucursal lleva su propia credencial —
            nunca el token de servicio del producto, que es el mismo para todos
            sus clientes.
          </p>
        </div>
        <Button onClick={empezarAlta}><Plus /> Agregar</Button>
      </header>

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      <div className="grid gap-4">
        {filas.map((s) => (
          <Card key={s.slug}>
            <CardContent className="space-y-3 pt-6">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{s.nombre}</span>
                <code className="text-xs text-muted-foreground">{s.url_base}</code>
                {s.cuit ? (
                  <Badge variant="outline">{s.razon_social || 'sin razón social'} · {s.cuit}</Badge>
                ) : (
                  <Badge variant="destructive">Sin CUIT: no se agrupa por razón social</Badge>
                )}
                {!s.tiene_credencial && (
                  <Badge variant="destructive">Sin credencial</Badge>
                )}
                {!s.activa && <Badge variant="secondary">Desactivada</Badge>}
                <div className="ml-auto flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => void probar(s.slug)}>
                    <Plug /> Probar
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => empezarEdicion(s)}>
                    <Pencil /> Editar
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => void borrar(s.slug)}>
                    <Trash2 />
                  </Button>
                </div>
              </div>

              {pruebas[s.slug] && (
                <p
                  className={pruebas[s.slug].ok ? 'text-sm text-muted-foreground' : 'text-sm text-destructive'}
                  data-testid={`prueba-${s.slug}`}
                >
                  {pruebas[s.slug].ok
                    ? `Contesta. Bloques: ${pruebas[s.slug].bloques?.join(', ')}. ` +
                      `Se identifica como ${pruebas[s.slug].identidad?.nombre || '(sin nombre)'} ` +
                      `CUIT ${pruebas[s.slug].identidad?.cuit || '(vacío)'}.`
                    : pruebas[s.slug].detalle}
                </p>
              )}

              <div className="flex flex-wrap items-center gap-4">
                <span className="text-xs text-muted-foreground">La ven:</span>
                {usuarios.map((u) => {
                  const asignado = (s.usuario_ids ?? []).includes(Number(u.id))
                  return (
                    <label key={u.id} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={asignado}
                        onCheckedChange={() => void alternarUsuario(s, Number(u.id))}
                      />
                      {u.name} <span className="text-muted-foreground">({u.role})</span>
                      {/* 🔑 El porcentaje sólo sobre los asignados: la
                          participación **no es lo que da acceso** ---eso lo da
                          la asignación--- así que ofrecerlo sobre alguien que no
                          ve la sucursal sugeriría que cargarlo se la da. El
                          backend además lo rechaza con un 409. */}
                      {asignado && (
                        <span className="flex items-center gap-1">
                          <Input
                            type="number"
                            min={0}
                            max={100}
                            step="0.01"
                            aria-label={`Participación de ${u.name} en ${s.nombre}`}
                            className="h-7 w-20"
                            defaultValue={s.participaciones?.[String(u.id)] ?? 0}
                            onBlur={(e) =>
                              void guardarParticipacion(s, Number(u.id), e.target.value)
                            }
                          />
                          <span className="text-muted-foreground">%</span>
                        </span>
                      )}
                    </label>
                  )
                })}
              </div>
              {/* ⚠️ **Se avisa, no se rechaza.** Las participaciones se cargan
                  de a una, así que un estado intermedio que no suma 100 es
                  normal mientras se completa; bloquear ahí obligaría a cargar
                  todo de un saque. Lo que no puede pasar es que quede mal y
                  nadie lo note. */}
              {(() => {
                const suma = Object.entries(s.participaciones ?? {})
                  .filter(([uid]) => (s.usuario_ids ?? []).includes(Number(uid)))
                  .reduce((t, [, p]) => t + p, 0)
                if (suma === 0 || Math.abs(suma - 100) < 0.01) return null
                return (
                  <p className="text-xs text-amber-700 dark:text-amber-400">
                    Las participaciones de esta sucursal suman {suma.toFixed(2)} %, no 100 %.
                  </p>
                )
              })()}
            </CardContent>
          </Card>
        ))}
        {filas.length === 0 && (
          <p className="text-sm text-muted-foreground">Todavía no hay sucursales cargadas.</p>
        )}
      </div>

      <Dialog open={editando !== null} onOpenChange={(v) => !v && setEditando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editando === 'nueva' ? 'Nueva sucursal' : 'Editar sucursal'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {editando === 'nueva' && (
              <div className="space-y-1">
                <Label htmlFor="slug">Identificador</Label>
                <Input
                  id="slug" value={form.slug}
                  onChange={(e) => setForm({ ...form, slug: e.target.value })}
                />
              </div>
            )}
            <div className="space-y-1">
              <Label htmlFor="nombre">Nombre</Label>
              <Input
                id="nombre" value={form.nombre}
                onChange={(e) => setForm({ ...form, nombre: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="url">URL</Label>
              <Input
                id="url" value={form.url_base} placeholder="http://contalibra:8000"
                onChange={(e) => setForm({ ...form, url_base: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                El nombre del contenedor en la red de control. Así el tráfico del
                panel no sale a internet.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="cuit">CUIT</Label>
                <Input
                  id="cuit" value={form.cuit}
                  onChange={(e) => setForm({ ...form, cuit: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="razon">Razón social</Label>
                <Input
                  id="razon" value={form.razon_social}
                  onChange={(e) => setForm({ ...form, razon_social: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="credencial">Credencial de panel</Label>
              <Input
                id="credencial" type="password" value={form.credencial}
                autoComplete="new-password"
                onChange={(e) => setForm({ ...form, credencial: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                {editando === 'nueva'
                  ? 'El LIBRA_PANEL_TOKEN de esa sucursal. Se guarda cifrada y no vuelve a mostrarse.'
                  : 'Vacío = dejar la que ya tiene. Escribir una nueva la reemplaza.'}
              </p>
            </div>
            <div className="space-y-1">
              <Label htmlFor="ruta">Ruta de usuarios</Label>
              <Input
                id="ruta" value={form.ruta_de_usuarios} placeholder="/api/usuarios"
                onChange={(e) => setForm({ ...form, ruta_de_usuarios: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                Dónde expone esta sucursal su ABM de usuarios, para dar de alta
                empleados. <code>/api/usuarios</code> en LibraClub, LibraCargo,
                LibraDesk, Contalibra y Restolibra; <code>/users</code> en
                VentaLibra, MedLibra y Gestiolibra.
              </p>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={form.activa}
                onCheckedChange={(v) => setForm({ ...form, activa: Boolean(v) })}
              />
              Activa (se consulta y cuenta para el total)
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditando(null)}>Cancelar</Button>
            <Button onClick={() => void guardar()}>Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
