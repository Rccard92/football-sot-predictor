import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { firstAllowedPath, tabKeyForPathname } from '../../config/tabAccess'
import { useAuth } from '../../contexts/AuthContext'

/** Una scheda non assegnata non si apre nemmeno scrivendo l'indirizzo a mano: si va alla prima consentita. */
export function TabGuard({ children }: { children: ReactNode }) {
  const { canSee, isAdmin, allowedTabs } = useAuth()
  const { pathname } = useLocation()
  if (canSee(tabKeyForPathname(pathname))) return <>{children}</>
  const target = firstAllowedPath(isAdmin, allowedTabs)
  if (target && target !== pathname) return <Navigate to={target} replace />
  return (
    <div className="mx-auto max-w-md rounded-xl border border-slate-200/80 bg-white p-5 text-sm text-slate-600 shadow-sm">
      Al tuo account non è ancora stata assegnata nessuna scheda. Chiedi all&apos;amministratore di abilitarla.
    </div>
  )
}
