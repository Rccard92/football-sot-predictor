import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Con BACKEND_PROXY_TARGET (variabile del servizio frontend su Railway) le chiamate /api passano dal dominio
// del frontend al backend: il cookie di sessione diventa "di prima parte" e il login regge anche su
// Safari/iPhone, che blocca i cookie di un dominio diverso (29/10/2026).
const backendProxyTarget = process.env.BACKEND_PROXY_TARGET?.replace(/\/+$/, '')

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  preview: {
    host: '0.0.0.0',
    port: Number(process.env.PORT) || 8080,
    allowedHosts: ['.up.railway.app'],
    proxy: backendProxyTarget
      ? { '/api': { target: backendProxyTarget, changeOrigin: true, xfwd: true, secure: true } }
      : undefined,
  },
  server: {
    host: '0.0.0.0',
    port: 8080,
    allowedHosts: ['.up.railway.app'],
  },
})
