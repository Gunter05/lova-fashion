import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // In local dev, proxy /api/v1/* to the FastAPI backend.
      // In production (Vercel), VITE_API_URL points directly to Render
      // and the /api/v1/... paths are used verbatim — no rewrite needed.
      '/api/v1': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
