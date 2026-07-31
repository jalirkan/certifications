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
