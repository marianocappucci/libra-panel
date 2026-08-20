// Cliente HTTP y tipos del panel.
//
// El cliente base (`ApiError` / `api`) viene de `libra-ui/api-client`, igual
// que en los seis productos y en el backoffice. Los tipos de acá para abajo
// son propios del panel.
export { api, ApiError } from 'libra-ui/api-client'

import { api } from 'libra-ui/api-client'

/** Roles del panel. `admin` somos nosotros; `socio` es el cliente que mira. */
export type Rol = 'admin' | 'socio'

export type Usuario = {
  id: string
  username: string
  name: string
  email?: string
  role: Rol
  active: boolean
}

export type Sucursal = {
  slug: string
  nombre: string
  url_base: string
  cuit: string
  razon_social: string
  activa: boolean
  /** Nunca viene la credencial en sí: sólo si hay una cargada. */
  tiene_credencial: boolean
  /** Sólo en el listado de admin. */
  usuario_ids?: number[]
}

/** Un bloque consolidado, con **de cuántas sucursales salió**.
 *
 * 🔴 `sucursales` puede ser menor que `cobertura.respondieron` sin que nada
 * esté mal: significa que las otras no miden ese bloque. Un bloque que nadie
 * reportó directamente no viene en el objeto — no viene en cero.
 */
export type Bloque = {
  datos: Record<string, unknown>
  sucursales: number
  slugs: string[]
  /** Claves que no estaban en todas las sucursales que sí mandaron el bloque. */
  incompletos: string[]
}

export type Cobertura = {
  total: number
  respondieron: number
  parcial: boolean
  sin_respuesta: { slug: string; nombre: string; detalle: string }[]
}

export type Grupo = {
  clave: string
  /** `false` = sucursal sin CUIT cargado. **No se agrupa con ninguna otra.** */
  identificado: boolean
  cuit: string
  razon_social: string
  sucursales: string[]
  cobertura: Cobertura
  bloques: Record<string, Bloque>
}

export type FilaSucursal = {
  slug: string
  nombre: string
  cuit: string
  razon_social: string
  estado: 'ok' | 'sin_respuesta'
  detalle: string
  identidad: { nombre: string; cuit: string; punto_venta: number | null }
  /** Contestó, pero no tiene empresa configurada. */
  identidad_incompleta: boolean
  /** El registro dice un CUIT y la sucursal informa otro. */
  cuit_discrepa: boolean
  bloques: Record<string, Record<string, unknown>>
}

export type Resumen = {
  periodo: { desde: string; hasta: string }
  cobertura: Cobertura
  consolidado: Record<string, Bloque>
  grupos: Grupo[]
  sucursales: FilaSucursal[]
}

export type PruebaSucursal = {
  slug: string
  ok: boolean
  detalle: string
  identidad?: { nombre: string; cuit: string; punto_venta: number | null }
  bloques?: string[]
}

export const panel = {
  // 🔴 Sin caché en ningún lado, ni acá ni en el backend: cachear un total
  // parcial lo deja pegado después de que la sucursal volvió. Cada pedido
  // vuelve a preguntarle a las N sucursales.
  resumen: (desde: string, hasta: string) =>
    api.get<Resumen>(`/api/resumen?desde=${desde}&hasta=${hasta}`),
  misSucursales: () => api.get<Sucursal[]>('/api/mis-sucursales'),

  // Sólo admin de acá para abajo.
  sucursales: () => api.get<Sucursal[]>('/api/sucursales'),
  crearSucursal: (datos: Partial<Sucursal> & { credencial?: string }) =>
    api.post<Sucursal>('/api/sucursales', datos),
  editarSucursal: (slug: string, datos: Partial<Sucursal> & { credencial?: string }) =>
    api.put<Sucursal>(`/api/sucursales/${slug}`, datos),
  borrarSucursal: (slug: string) => api.del<void>(`/api/sucursales/${slug}`),
  asignar: (slug: string, usuario_ids: number[]) =>
    api.put<{ slug: string; usuario_ids: number[] }>(
      `/api/sucursales/${slug}/usuarios`, { usuario_ids },
    ),
  probar: (slug: string) => api.post<PruebaSucursal>(`/api/sucursales/${slug}/probar`),
  usuarios: () => api.get<Usuario[]>('/api/usuarios'),
}

/** Ruta del ABM de usuarios, para la prop `basePath` del componente de libra-ui. */
export const RUTA_USUARIOS = '/api/usuarios'
