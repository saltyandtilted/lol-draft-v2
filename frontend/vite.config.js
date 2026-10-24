import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Forward /api calls to the Flask backend so the browser sees one origin (no CORS needed).
    proxy: {
      '/api': 'http://127.0.0.1:5001',
    },
  },
})
