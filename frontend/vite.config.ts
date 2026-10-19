import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Forward API calls to the FastAPI backend so the session cookie stays same-origin in dev.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
