// Recupero de contraseña por correo.
//
// Sin `basePath`: el default de libra-ui es `/auth`, que es exactamente donde
// el panel monta su router de auth. Ver el comentario de `auth.ts` para por qué
// ese prefijo y no `/api/auth`.
import { createForgotPassword, createResetPassword } from 'libra-ui/PasswordReset'

const COMUN = { productName: 'Panel', productInitial: 'P' }

export const OlvideMiPassword = createForgotPassword(COMUN)
export const ResetearPassword = createResetPassword(COMUN)
