import { useCallback, useEffect, useState } from 'react'
import { adminLogin, adminLogout, getAdminSession } from '../lib/adminAuthApi'
import {
  ADMIN_AUTH_CHANGED_EVENT,
  ADMIN_AUTH_REQUIRED_EVENT,
  announceAdminAuthChanged,
  requestAdminLogin,
} from '../lib/adminAuthEvents'
import { AdminHttpError } from '../lib/api'

/** Dialogo di accesso amministratore, aperto quando un'operazione protetta torna 401 o dal pulsante
 *  "Admin" del menu. La password resta solo nello stato del form per il tempo della richiesta. */
export function AdminSessionGate() {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    const onRequired = (e: Event) => {
      const detail = (e as CustomEvent<{ reason?: string }>).detail
      setReason(detail?.reason ?? null)
      setError(null)
      setDone(false)
      setOpen(true)
    }
    window.addEventListener(ADMIN_AUTH_REQUIRED_EVENT, onRequired)
    return () => window.removeEventListener(ADMIN_AUTH_REQUIRED_EVENT, onRequired)
  }, [])

  const close = useCallback(() => {
    setOpen(false)
    setPassword('')
    setError(null)
  }, [])

  const submit = async () => {
    if (!password) {
      setError('Inserisci la password amministratore.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await adminLogin(password)
      setPassword('')
      setDone(true)
      announceAdminAuthChanged(true)
    } catch (e) {
      if (e instanceof AdminHttpError && e.status === 503) {
        setError('Accesso amministratore non configurato sul server.')
      } else if (e instanceof AdminHttpError && e.status === 429) {
        setError('Troppi tentativi: riprova tra qualche minuto.')
      } else {
        setError(e instanceof Error ? e.message : 'Accesso non riuscito')
      }
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Accesso amministratore"
      data-testid="admin-session-gate"
    >
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl">
        <h2 className="text-base font-semibold text-slate-900">Accesso amministratore</h2>
        {done ? (
          <>
            <p className="mt-2 text-sm text-slate-700">Accesso eseguito per 12 ore. Ripeti l&apos;operazione.</p>
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
          <form
            className="mt-2 space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              void submit()
            }}
          >
            <p className="text-sm text-slate-600">
              {reason ?? 'Questa operazione modifica dati o usa le chiamate API: serve la password amministratore.'}
            </p>
            <input
              type="password"
              autoComplete="current-password"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              placeholder="Password amministratore"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              aria-label="Password amministratore"
            />
            {error ? <p className="text-sm text-rose-700">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                onClick={close}
                disabled={busy}
              >
                Annulla
              </button>
              <button
                type="submit"
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
                disabled={busy}
              >
                {busy ? 'Accesso…' : 'Accedi'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

/** Pulsante in fondo al menu: mostra se la sessione amministratore e' attiva, apre l'accesso o esce. */
export function AdminSessionButton({ collapsed }: { collapsed: boolean }) {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null)

  const refresh = useCallback(() => {
    getAdminSession()
      .then((s) => setAuthenticated(Boolean(s.authenticated)))
      .catch(() => setAuthenticated(false))
  }, [])

  useEffect(() => {
    refresh()
    const onChanged = () => refresh()
    window.addEventListener(ADMIN_AUTH_CHANGED_EVENT, onChanged)
    window.addEventListener(ADMIN_AUTH_REQUIRED_EVENT, onChanged)
    return () => {
      window.removeEventListener(ADMIN_AUTH_CHANGED_EVENT, onChanged)
      window.removeEventListener(ADMIN_AUTH_REQUIRED_EVENT, onChanged)
    }
  }, [refresh])

  const onClick = () => {
    if (authenticated) {
      adminLogout()
        .catch(() => undefined)
        .finally(() => {
          setAuthenticated(false)
          announceAdminAuthChanged(false)
        })
    } else {
      requestAdminLogin('Accedi come amministratore per usare scansioni, aggiornamenti e strumenti di gestione.')
    }
  }

  const label = authenticated ? 'Admin attivo · esci' : 'Accedi come admin'
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      data-testid="admin-session-button"
      className={`mb-2 flex w-full items-center rounded-xl border text-xs font-medium transition-colors ${
        authenticated
          ? 'border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
          : 'border-slate-200/80 bg-white text-slate-600 hover:bg-slate-50'
      } ${collapsed ? 'justify-center p-2.5' : 'gap-2 px-3 py-2'}`}
    >
      <span aria-hidden>{authenticated ? '●' : '○'}</span>
      {!collapsed ? <span>{label}</span> : null}
    </button>
  )
}
