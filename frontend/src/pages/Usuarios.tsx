// ABM de usuarios del panel. **Sólo admin.**
//
// La pantalla es la de libra-ui tal cual; lo único propio es la ruta del
// router, que en este producto cuelga de `/api/usuarios`.
import { Usuarios as UsuariosDeLibraUi } from 'libra-ui/Usuarios'

import { RUTA_USUARIOS } from '../api'

export function Usuarios() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Usuarios</h1>
        <p className="text-sm text-muted-foreground">
          Un <strong>socio</strong> ve los números de las sucursales que tenga
          asignadas y nada más. Las asignaciones se editan en Sucursales.
        </p>
      </header>
      <UsuariosDeLibraUi basePath={RUTA_USUARIOS} />
    </div>
  )
}
