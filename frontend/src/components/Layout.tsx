// Shim sobre `libra-ui/Layout`, con el `useAuth` propio del panel.
//
// El branding es genérico a propósito: el panel es transversal —sirve para un
// grupo de sucursales de Contalibra igual que para uno de VentaLibra— y el
// nombre real llega por `PANEL_NAME` del entorno. Poner un nombre acá
// obligaría a una imagen por cliente, que es justo lo que este repo evita.
import { Building2, LayoutDashboard, Users } from 'lucide-react'
import { createLayout } from 'libra-ui/Layout'

import { useAuth } from '../auth'
import type { Usuario } from '../api'

export const Layout = createLayout<Usuario>({
  productName: 'Panel',
  productInitial: 'P',
  icon: LayoutDashboard,
  homeTo: '/panel',
  navItems: [
    { to: '/panel', label: 'Mis sucursales', icon: LayoutDashboard },
    // 🔴 `hideFor` esconde el ítem; **no es lo que protege la ruta**. El
    // cerrojo real es el `Depends(requiere_admin)` del backend, que contesta
    // 403 aunque alguien escriba la URL a mano. Esto es para que el socio no
    // vea una pantalla que no puede usar.
    {
      to: '/sucursales', label: 'Sucursales', icon: Building2,
      hideFor: (u) => u.role !== 'admin',
    },
    {
      to: '/usuarios', label: 'Usuarios', icon: Users,
      hideFor: (u) => u.role !== 'admin',
    },
  ],
  getUserName: (u) => u.name || u.username,
  getUserSubtitle: (u) => (u.role === 'admin' ? 'Administrador' : 'Socio'),
  useAuth,
})
