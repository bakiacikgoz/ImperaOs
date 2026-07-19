import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const productionCsp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' asset: http://asset.localhost data: blob:; font-src 'self' data:; connect-src ipc: http://ipc.localhost; worker-src 'self' blob:; object-src 'none'; frame-src 'none'; base-uri 'self'; form-action 'none'"

const cspSafeDependencyRoots = {
  name: 'csp-safe-dependency-roots',
  enforce: 'pre' as const,
  transform(source: string, id: string) {
    if (!id.includes('node_modules')) return null
    const code = source
      .replace(/\bFunction\(\s*(['"])return this\1\s*\)\(\)/g, 'globalThis')
      .replace(
        /\bFunction\(\s*(['"])r\1\s*,\s*(['"])regeneratorRuntime = r\2\s*\)\(([^)]*)\)/g,
        '((r) => { globalThis.regeneratorRuntime = r; })($3)',
      )
      .replace(
        /\bnew\s+Function\([^)]*\)/g,
        '(() => { throw new TypeError("dynamic code disabled by CSP"); })',
      )
    if (code === source) return null
    return {
      code,
      map: null,
    }
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [cspSafeDependencyRoots, react()],
  preview: {
    headers: {
      'Content-Security-Policy': productionCsp,
    },
  },
  worker: {
    format: 'es',
    plugins: () => [cspSafeDependencyRoots],
  },
  test: {
    environment: 'jsdom',
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    setupFiles: ['./src/test/setup.ts'],
    globals: false,
  },
})
