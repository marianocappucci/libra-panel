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
  /** Dónde vive el router de usuarios de esta sucursal, para dar de alta
   *  empleados.
   *
   *  🔴 **No es la misma en todos los productos.** Medido el 2026-08-29:
   *  `/api/usuarios` en LibraClub, LibraCargo, LibraDesk, Contalibra y
   *  Restolibra; **`/users`** en VentaLibra, MedLibra y Gestiolibra. El router
   *  de usuarios es de cada producto, no del kit de auth, así que no hay una
   *  convención que asumir. */
  ruta_de_usuarios: string
  /** Nunca viene la credencial en sí: sólo si hay una cargada. */
  tiene_credencial: boolean
  /** Sólo en el listado de admin. */
  usuario_ids?: number[]
  /** `{ "<usuario_id>": porcentaje }`. Las claves son texto porque JSON no
   *  tiene enteros por clave.
   *
   *  🔑 **Es un dato informativo: no cambia ningún número.** El socio ve la
   *  facturación completa de las sucursales donde participa. */
  participaciones?: Record<string, number>
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

/** Cómo salió el alta en UNA sucursal.
 *
 * 🔑 **`ya_estaba` no es una falla.** Es el caso normal de un empleado que ya
 * trabajaba en esa sede y ahora suma otra: la pantalla no lo pinta de rojo
 * porque no hay nada que arreglar. */
export type AltaEnSucursal = {
  slug: string
  nombre: string
  estado: 'creado' | 'ya_estaba' | 'sin_respuesta'
  detalle: string
}

/** El resultado del alta, **una fila por sucursal**.
 *
 * 🔴 Nunca es un éxito liso. El dueño tiene que poder ver en cuáles quedó dado
 * de alta y en cuáles no — que es justamente lo que hoy no puede saber cuando
 * los crea a mano, una instancia a la vez. */
export type AltaDeEmpleado = {
  username: string
  sucursales: AltaEnSucursal[]
  parcial: boolean
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
  /** El porcentaje de un socio en una sucursal. Va aparte de `asignar` a
   *  propósito: aquél fija **quién ve**, y es lo que da acceso. */
  participacion: (slug: string, usuario_id: number, participacion: number) =>
    api.put<{ slug: string; usuario_id: number; participacion: number }>(
      `/api/sucursales/${slug}/participacion`, { usuario_id, participacion },
    ),
  asignar: (slug: string, usuario_ids: number[]) =>
    api.put<{ slug: string; usuario_ids: number[] }>(
      `/api/sucursales/${slug}/usuarios`, { usuario_ids },
    ),
  probar: (slug: string) => api.post<PruebaSucursal>(`/api/sucursales/${slug}/probar`),
  usuarios: () => api.get<Usuario[]>('/api/usuarios'),
  /** Da de alta un empleado en varias sucursales de una.
   *
   * 🔑 **Sigue habiendo N usuarios, uno por sede, y eso es a propósito.** No es
   * SSO: cada instancia mantiene su sesión. Lo que cambia es que se crean desde
   * un solo lugar. La contraseña también es una por sede. */
  altaDeEmpleado: (datos: {
    username: string; name: string; password: string; role: string; slugs: string[]
  }) => api.post<AltaDeEmpleado>('/api/empleados', datos),
}

/** Ruta del ABM de usuarios, para la prop `basePath` del componente de libra-ui. */
export const RUTA_USUARIOS = '/api/usuarios'
