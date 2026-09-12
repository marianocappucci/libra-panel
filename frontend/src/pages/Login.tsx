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
  // Recuadro «No soy un robot» (ALTCHA, libra-ui v0.69.2). Lo sirve el router
  // de libraauth con `captcha=True`; libra-ui lo pinta sólo si esta ruta
  // contesta con un desafío, y deja «Ingresar» deshabilitado hasta tildarlo.
  captchaPath: '/auth/captcha',
})
