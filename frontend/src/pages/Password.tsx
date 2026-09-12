// Recupero de contraseña por correo.
//
// Sin `basePath`: el default de libra-ui es `/auth`, que es exactamente donde
// el panel monta su router de auth. Ver el comentario de `auth.ts` para por qué
// ese prefijo y no `/api/auth`.
import { createForgotPassword, createResetPassword } from 'libra-ui/PasswordReset'

const COMUN = { productName: 'Panel', productInitial: 'P' }

// El pedido del mail lleva el mismo captcha ALTCHA que el login: sin él, el
// endpoint manda correos a pedido de cualquiera. El reset-password no lo
// lleva: ya lo gatea el token que llegó por mail.
export const OlvideMiPassword = createForgotPassword({ ...COMUN, captchaPath: '/auth/captcha' })
export const ResetearPassword = createResetPassword(COMUN)
