import { createLogin } from 'libra-ui/Login'

import { useAuth } from '../auth'
import type { Usuario } from '../api'

export const Login = createLogin<Usuario>({
  productName: 'Panel',
  productInitial: 'P',
  redirectTo: '/panel',
  useAuth,
  // A diferencia del backoffice, acá el enlace SÍ va: las credenciales son
  // filas de una tabla, no variables de entorno, y `POST
  // /api/auth/forgot-password` existe. Es la mitad visible de por qué el panel
  // usa `SessionAuth`.
  forgotPasswordPath: '/forgot-password',
})
