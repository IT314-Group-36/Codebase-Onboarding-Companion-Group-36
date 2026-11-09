import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// VITE_PROXY_TARGET is set to http://api:8000 inside docker (dev stage); locally it defaults to localhost.
const apiTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
    // bind-mounted files in Docker (esp. Windows/macOS) don't emit fs events reliably
    watch: process.env.VITE_PROXY_TARGET ? { usePolling: true } : undefined,
  },
})
