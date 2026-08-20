// La pantalla. Los números de todas las sucursales del dueño, en vivo.
import { useCallback, useEffect, useState } from 'react'
import { Building2, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

import { ApiError, panel, type Resumen } from '../api'
import { Consolidado } from '../components/Bloques'
import { AvisoParcial, ContadorCobertura } from '../components/Cobertura'
import { hoyIso, periodoLegible, primerDiaDelMesIso } from '../lib/fecha'

export function Panel() {
  // Las fechas viven en ISO porque es lo que entiende `<input type="date">` y
  // lo que viaja por la API. El `dd-mm-aaaa` aparece sólo donde lo lee una
  // persona, y sale del helper único (`lib/fecha.ts`).
  const [desde, setDesde] = useState(primerDiaDelMesIso)
  const [hasta, setHasta] = useState(hoyIso)
  const [datos, setDatos] = useState<Resumen | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    setError(null)
    try {
      setDatos(await panel.resumen(desde, hasta))
    } catch (err) {
      // 🔴 Ante un error se BORRAN los datos viejos. Dejarlos en pantalla con
      // un cartel arriba es cómo se llega a que alguien lea los números del
      // mes pasado creyendo que son los de hoy.
      setDatos(null)
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setCargando(false)
    }
  }, [desde, hasta])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Mis sucursales</h1>
          {datos && (
            <p className="text-sm text-muted-foreground">
              {periodoLegible(datos.periodo.desde, datos.periodo.hasta)}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="desde" className="text-xs">Desde</Label>
            <Input
              id="desde" type="date" value={desde} max={hasta}
              onChange={(e) => setDesde(e.target.value)} className="w-40"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="hasta" className="text-xs">Hasta</Label>
            <Input
              id="hasta" type="date" value={hasta} min={desde}
              onChange={(e) => setHasta(e.target.value)} className="w-40"
            />
          </div>
          {/* Actualizar es volver a preguntarle a las N sucursales: no hay
              caché que refrescar. */}
          <Button variant="outline" onClick={() => void cargar()} disabled={cargando}>
            <RefreshCw className={cargando ? 'animate-spin' : ''} />
            Actualizar
          </Button>
        </div>
      </header>

      {error && (
        <p role="alert" className="text-sm text-destructive">{error}</p>
      )}

      {cargando && !datos && (
        <p className="text-sm text-muted-foreground">Preguntándole a cada sucursal…</p>
      )}

      {datos && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <ContadorCobertura cobertura={datos.cobertura} />
            <span className="text-sm text-muted-foreground">
              en vivo, sin caché
            </span>
          </div>
          <AvisoParcial cobertura={datos.cobertura} />

          <Tabs defaultValue="todo">
            <TabsList>
              <TabsTrigger value="todo">Todas juntas</TabsTrigger>
              <TabsTrigger value="cuit">Por razón social</TabsTrigger>
              <TabsTrigger value="sucursales">Sucursal por sucursal</TabsTrigger>
            </TabsList>

            <TabsContent value="todo" className="mt-4 space-y-4">
              {/* El aviso que evita el error más caro de leer esta pantalla:
                  este número sirve para mirar el negocio, no para presentar. */}
              <p className="rounded-md bg-muted/50 p-3 text-sm text-muted-foreground">
                Sumando entre CUITs distintos, este total es un <strong>número de
                gestión</strong> y no una cifra declarable: cada razón social tiene su
                propio libro de IVA. El que cierra contra los libros está en «Por
                razón social».
              </p>
              <Consolidado
                bloques={datos.consolidado}
                respondieron={datos.cobertura.respondieron}
              />
            </TabsContent>

            <TabsContent value="cuit" className="mt-4 space-y-8">
              {datos.grupos.map((g) => (
                <section key={g.clave} className="space-y-3">
                  <div className="flex flex-wrap items-center gap-3 border-b pb-2">
                    <h2 className="text-lg font-semibold tracking-tight">
                      {g.razon_social || 'Sin nombre'}
                    </h2>
                    {g.identificado ? (
                      <Badge variant="outline">CUIT {g.cuit}</Badge>
                    ) : (
                      // 🔴 Una sucursal sin CUIT cargado va SOLA y nombrada.
                      // Agruparla con las otras sin CUIT las juntaría como si
                      // fueran la misma empresa.
                      <Badge variant="destructive" data-testid="sin-identificar">
                        Sin identificar — falta cargarle el CUIT
                      </Badge>
                    )}
                    <ContadorCobertura cobertura={g.cobertura} />
                  </div>
                  <AvisoParcial cobertura={g.cobertura} />
                  <Consolidado
                    bloques={g.bloques} respondieron={g.cobertura.respondieron}
                  />
                </section>
              ))}
            </TabsContent>

            <TabsContent value="sucursales" className="mt-4 grid gap-4 lg:grid-cols-2">
              {datos.sucursales.map((s) => (
                <Card key={s.slug} data-testid={`sucursal-${s.slug}`}>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                      <Building2 className="size-4 text-muted-foreground" />
                      {s.nombre}
                      {s.estado === 'ok' ? (
                        <Badge variant="secondary">Contestó</Badge>
                      ) : (
                        <Badge variant="destructive">Sin respuesta</Badge>
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {s.estado === 'sin_respuesta' ? (
                      <p className="text-sm text-muted-foreground">
                        {/* Se dice el motivo, no un "error" genérico: es lo que
                            distingue "está apagada" de "la credencial está mal". */}
                        {s.detalle}
                      </p>
                    ) : (
                      <>
                        {s.identidad_incompleta && (
                          <p className="text-sm text-destructive" data-testid="identidad-incompleta">
                            Contestó, pero no tiene empresa configurada: sin CUIT no
                            se la puede agrupar por razón social.
                          </p>
                        )}
                        {s.cuit_discrepa && (
                          <p className="text-sm text-destructive" data-testid="cuit-discrepa">
                            El CUIT cargado en el panel ({s.cuit}) no coincide con el
                            que informa la sucursal ({s.identidad.cuit}).
                          </p>
                        )}
                        <Consolidado
                          respondieron={1}
                          bloques={Object.fromEntries(
                            Object.entries(s.bloques).map(([nombre, datosBloque]) => [
                              nombre,
                              { datos: datosBloque, sucursales: 1, slugs: [s.slug], incompletos: [] },
                            ]),
                          )}
                        />
                      </>
                    )}
                  </CardContent>
                </Card>
              ))}
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  )
}
