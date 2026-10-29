import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { ADMIN_AUTH_REQUIRED_EVENT, announceAdminAuthChanged } from '../lib/adminAuthEvents'
import { LoginForm } from './auth/LoginForm'

/** Dialogo di accesso, aperto quando un'operazione da amministratore torna 401 o dal pulsante "Accedi" del
 *  menu. Dal 29/10/2026 si entra con email e password dell'account (oppure email `admin` e la password
 *  amministratore storica, come accesso di emergenza). */
export function AdminSessionGate() {
  const { refresh } = useAuth()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    const onRequired = (e: Event) => {
      const detail = (e as CustomEvent<{ reason?: string }>).detail
      setReason(detail?.reason ?? null)
      setDone(false)
      setOpen(true)
    }
    window.addEventListener(ADMIN_AUTH_REQUIRED_EVENT, onRequired)
    return () => window.removeEventListener(ADMIN_AUTH_REQUIRED_EVENT, onRequired)
  }, [])

  const close = useCallback(() => setOpen(false), [])

  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Accesso"
      data-testid="admin-session-gate"
    >
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl">
        <h2 className="text-base font-semibold text-slate-900">Accesso</h2>
        {done ? (
          <>
            <p className="mt-2 text-sm text-slate-700">Accesso eseguito. Ripeti l&apos;operazione.</p>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
                onClick={close}
              >
                Ok
              </button>
            </div>
          </>
        ) : (
          <div className="mt-2 space-y-3">
            <p className="text-sm text-slate-600">
              {reason ?? 'Questa operazione modifica dati o usa le chiamate API: serve un account amministratore.'}
            </p>
            <LoginForm
              onSuccess={async () => {
                setDone(true)
                announceAdminAuthChanged(true)
                await refresh()
              }}
            />
            <div className="flex justify-end">
              <button
                type="button"
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                onClick={close}
              >
                Annulla
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
