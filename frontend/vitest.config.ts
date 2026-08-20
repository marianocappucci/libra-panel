// Config de tests aparte del vite.config.ts, y no un bloque `test` dentro de
// él: así el build de producción no arrastra tipos ni opciones de Vitest. Se
// reusa la config de Vite (con su alias `@`) via mergeConfig, para que los
// tests resuelvan los imports igual que la app.
import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    // `@vitejs/plugin-react` no toca node_modules, así que los .tsx de
    // libra-ui los transpila esbuild -- y por defecto usa el runtime CLÁSICO,
    // que emite `React.createElement` sin que React esté importado: "React is
    // not defined" al primer render.
    esbuild: { jsx: 'automatic' },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      // La zona horaria se fija acá y no se hereda de la máquina: el panel
      // formatea fechas y el mes en curso en hora de Argentina, y una máquina
      // en UTC da otro resultado durante las últimas tres horas del día.
      // Estándar de la familia desde el 2026-08-12 (referencia: LibraDesk).
      env: { TZ: 'America/Argentina/Buenos_Aires' },
      coverage: {
        provider: 'v8',
        // Trinquete, no meta: sirve para que nadie borre tests. La lógica
        // compartida (Login, Layout, tabla, Usuarios) se prueba a fondo en
        // libra-ui, que tiene su propia suite y su propio CI; acá se prueba
        // lo propio del panel, que es cómo se LEE un total parcial.
        thresholds: { lines: 84 },
        reporter: ['text-summary', 'json-summary'],
        include: ['src/**/*.{ts,tsx}'],
        exclude: [
          'src/test/**',
          'src/**/*.d.ts',
          'src/main.tsx',
          'src/components/ui/**', // shadcn/ui: copiado tal cual del upstream
          'src/components/data-table.tsx',
          'src/hooks/**',
          'src/lib/utils.ts',
          // Shims de una línea sobre las factories de libra-ui: toda la lógica
          // (formulario, errores, redirecciones) vive allá y tiene su propia
          // suite. Medirlos acá contaría dos veces lo mismo y, peor, daría un
          // número de cobertura que no corresponde a ningún test propio.
          'src/pages/Login.tsx',
          'src/pages/Password.tsx',
          'src/pages/Usuarios.tsx',
          'src/components/Layout.tsx',
        ],
      },
      server: {
        deps: {
          // `libra-ui` se consume como CÓDIGO FUENTE (.tsx) desde
          // node_modules -- sus `exports` apuntan a src/. Vitest por defecto
          // no transforma node_modules, así que ese JSX llegaría sin compilar.
          inline: ['libra-ui'],
        },
      },
    },
  }),
)
