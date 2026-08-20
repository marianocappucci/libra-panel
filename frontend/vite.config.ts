import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// La API del panel cuelga de tres prefijos: `/api`, `/auth` y `/health`. El
// de auth va aparte porque el router de libraauth se monta en `/auth`, que es
// donde `CambiarPassword` de libra-ui lo busca hardcodeado — ver el comentario
// de `src/auth.ts`.
//
// Se usa la forma con regex y `(?:/|$)` igual que en el resto de la familia,
// para que agregar una ruta de la SPA que empiece igual —`/apitest`— no se
// vuelva un problema silencioso.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // Lo que hace que `libra-ui` funcione: sus componentes importan los
      // primitivos de shadcn como `@/components/ui/...`, y Vite aplica este
      // alias también al código que viene de `node_modules`. Así cada
      // consumidor compila libra-ui contra SUS primitivos shadcn, que es
      // justo el punto de que shadcn se distribuya como código copiado.
      '@': new URL('./src', import.meta.url).pathname,
    },
  },
  server: {
    proxy: {
      '^/api(?:/|$)': { target: 'http://localhost:8000', changeOrigin: true },
      '^/auth(?:/|$)': { target: 'http://localhost:8000', changeOrigin: true },
      '^/health(?:/|$)': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
