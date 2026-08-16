import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * Build output lands in ../web so serve.py keeps serving it with no Python
 * change. Nothing is fetched at runtime: assets are relative, everything is
 * bundled, and there are no CDN or font requests anywhere in the app.
 */
export default defineConfig({
  plugins: [react()],
  base: './',
  resolve: {
    alias: {
      /*
       * kokoro-js imports `phonemizer`, which embeds espeak-ng as an Emscripten
       * module. Minifying it leaves espeak with an empty language table and
       * every call fails with `Invalid language identifier: "en-us"`. The same
       * file served unbundled works. So the import is redirected to a shim that
       * fetches the untouched copy from /models/runtime/ at runtime.
       * See src/lib/phonemizer-shim.ts.
       */
      phonemizer: fileURLToPath(new URL('./src/lib/phonemizer-shim.ts', import.meta.url)),
    },
  },
  build: {
    outDir: '../web',
    emptyOutDir: true,
    assetsDir: 'assets',
    sourcemap: false,
    // One chunk for the charting library keeps the initial parse small without
    // splitting the app into requests that a cold local server has to serialise.
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/recharts') || id.includes('node_modules/victory')) {
            return 'charts'
          }
          return undefined
        },
      },
    },
  },
  server: {
    port: 5173,
    // `npm run dev` proxies the API to the Python server so the real engine
    // backs the dev loop. Start it with: python serve.py --no-browser
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: false,
      },
    },
  },
})
