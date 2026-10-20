import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Toaster } from 'sonner'
import './index.css'
import App from './App.tsx'
import { installAdminFetchInterceptor } from './lib/adminAuthEvents'

// sessione admin su tutte le richieste al backend e login automatico sui 401 dell'area admin (20/10/2026)
installAdminFetchInterceptor(import.meta.env.VITE_API_BASE_URL)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <Toaster richColors position="top-right" />
  </StrictMode>,
)
