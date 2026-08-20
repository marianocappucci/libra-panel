// Sesión del usuario del panel.
//
// Se usa la factory `createAuthContext` de libra-ui y no la instancia
// pre-configurada porque el tipo de usuario es propio del panel (`Rol` es
// `'admin' | 'socio'`, no `'admin' | 'staff'`). Las rutas sí son las de
// siempre: `/auth/*`.
//
// 🔴 **El prefijo `/auth` no es una preferencia estética.** El componente
// `CambiarPassword` que monta el Layout de libra-ui pega contra
// `/auth/change-password` **hardcodeado**, sin prop para cambiarlo. Con la auth
// montada en `/api/auth`, esa ruta no existiría — y como los productos de esta
// familia sirven su SPA con fallback, el `POST` recibiría **200 con el
// index.html** en vez de un 404. O sea: el botón de cambiar la contraseña
// fallaría sin decir por qué.
//
// A diferencia del backoffice, acá el usuario **sí** es una fila de una tabla:
// tiene id, nombre y rol, y puede cambiarse la contraseña sin que nadie
// redespliegue nada. Es la diferencia entre `SessionAuth` y `AdminAuth`.
import { createAuthContext } from 'libra-ui/AuthContext'

import type { Usuario } from './api'

export const { AuthProvider, useAuth } = createAuthContext<Usuario>({
  mePath: '/auth/me',
  loginPath: '/auth/login',
  logoutPath: '/auth/logout',
})

/** `true` si este usuario administra el registro (o sea: somos nosotros). */
export function esAdmin(usuario: Usuario | null): boolean {
  return usuario?.role === 'admin'
}
