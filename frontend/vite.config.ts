import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  preview: {
    host: '0.0.0.0',
    port: Number(process.env.PORT) || 8080,
    allowedHosts: ['frontend-production-9b20.up.railway.app'],
  },
  server: {
    host: '0.0.0.0',
    port: 8080,
    allowedHosts: ['frontend-production-9b20.up.railway.app'],
  },
})
