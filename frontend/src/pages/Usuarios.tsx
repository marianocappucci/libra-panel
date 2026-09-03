// ABM de usuarios del panel. **Sólo admin.**
//
// La pantalla es la de libra-ui tal cual; lo único propio es la ruta del
// router, que en este producto cuelga de `/api/usuarios`, y la aclaración
// sobre qué ve un socio, que es vocabulario de este producto.
//
// El título lo pone libra-ui (`TituloPantalla`, con el icono que el sidebar
// le da a la pantalla — acá `Users`, ver `components/Layout.tsx`). Esta
// página escribía el suyo a mano; dejarlo mostraría "Usuarios" dos veces,
// uno arriba del otro.
import { Users } from 'lucide-react'
import { Usuarios as UsuariosDeLibraUi } from 'libra-ui/Usuarios'

import { RUTA_USUARIOS } from '../api'

export function Usuarios() {
  return (
    <div className="space-y-6">
      <UsuariosDeLibraUi basePath={RUTA_USUARIOS} icono={Users} />
      <p className="text-sm text-muted-foreground">
        Un <strong>socio</strong> ve los números de las sucursales que tenga
        asignadas y nada más. Las asignaciones se editan en Sucursales.
      </p>
    </div>
  )
}
