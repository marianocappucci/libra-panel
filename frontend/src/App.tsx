import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { esAdmin, useAuth } from './auth'
import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { OlvideMiPassword, ResetearPassword } from './pages/Password'
import { Empleados } from './pages/Empleados'
import { Panel } from './pages/Panel'
import { Sucursales } from './pages/Sucursales'
import { Usuarios } from './pages/Usuarios'

function RutaProtegida({ children, soloAdmin = false }: { children: ReactNode; soloAdmin?: boolean }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Cargando…
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  // Se manda al panel y no a un 403: el socio no hizo nada mal, esa pantalla
  // no es para él. El cerrojo que importa está en el backend.
  if (soloAdmin && !esAdmin(user)) return <Navigate to="/panel" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      {/* Estas dos sí existen, a diferencia del backoffice: las credenciales
          del panel son filas de una tabla y `libraauth` expone el recupero. */}
      <Route path="/forgot-password" element={<OlvideMiPassword />} />
      <Route path="/reset-password" element={<ResetearPassword />} />
      <Route path="/panel" element={<RutaProtegida><Panel /></RutaProtegida>} />
      <Route
        path="/sucursales"
        element={<RutaProtegida soloAdmin><Sucursales /></RutaProtegida>}
      />
      <Route
        path="/usuarios"
        element={<RutaProtegida soloAdmin><Usuarios /></RutaProtegida>}
      />
      <Route
        path="/empleados"
        element={<RutaProtegida soloAdmin><Empleados /></RutaProtegida>}
      />
      <Route path="*" element={<Navigate to="/panel" replace />} />
    </Routes>
  )
}
