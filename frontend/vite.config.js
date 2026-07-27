import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Auth endpoints: /api/auth/* → /api/v1/auth/*
      '/api/auth': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/auth/, '/api/v1/auth'),
      },
      // Profile endpoints: /api/users/* and /api/admin/* → /api/v1/*
      '/api/users': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/users/, '/api/v1/users'),
      },
      '/api/admin': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/admin/, '/api/v1/admin'),
      },
      // Measurements: /api/measurements/* → /api/v1/measurements/*
      '/api/measurements': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/measurements/, '/api/v1/measurements'),
      },
      // Fabrics & categories: /api/fabrics|categories → /api/v1/...
      '/api/fabrics': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/fabrics/, '/api/v1/fabrics'),
      },
      '/api/categories': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/categories/, '/api/v1/categories'),
      },
      // Pattern catalog: /api/models/* → /api/v1/models/*
      '/api/models': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/models/, '/api/v1/models'),
      },
      // Ease margins: /api/ease/* → /api/v1/ease/*
      '/api/ease': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/ease/, '/api/v1/ease'),
      },
      // Reports: /api/reports/* → /api/v1/reports/*
      '/api/reports': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/reports/, '/api/v1/reports'),
      },
    },
  },
})

