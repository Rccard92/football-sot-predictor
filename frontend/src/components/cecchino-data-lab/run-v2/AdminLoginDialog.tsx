import { useState } from 'react'
import { AdminHttpError } from '../../../lib/api'
import { adminLogin } from '../../../lib/adminAuthApi'

type Props = {
  onClose: () => void
  onSuccess: () => void
}

/** Login della sessione admin: la password resta nello stato locale del form
 *  per il tempo della richiesta e non viene mai persistita. */
export function AdminLoginDialog({ onClose, onSuccess }: Props) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!password) {
      setError('Inserire la password admin.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await adminLogin(password)
      setPassword('')
      onSuccess()
    } catch (e) {
      if (e instanceof AdminHttpError && e.status === 503) {
        setError(
          'Autenticazione admin non configurata sul server: mancano ADMIN_PASSWORD e ADMIN_SESSION_SECRET.',
        )
      } else {
        setError(e instanceof Error ? e.message : 'Login fallito')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Login admin"
      data-testid="run-v2-login-dialog"
    >
      <div className="lab-card w-full max-w-sm rounded-xl p-5">
        <h3 className="text-lg font-semibold">Sessione admin richiesta</h3>
        <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
          Avvio, resume e annullamento di una RUN V2 sono operazioni di controllo: servono le
          credenziali amministrative.
        </p>
        <form
          className="mt-4 space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <label className="block text-sm">
            <span className="mb-1 block" style={{ color: 'var(--lab-muted)' }}>
              Password admin
            </span>
            <input
              type="password"
              autoFocus
              autoComplete="current-password"
              className="w-full rounded-md border bg-transparent px-3 py-2 text-sm"
              style={{ borderColor: 'var(--lab-border)' }}
              data-testid="run-v2-login-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <p className="text-sm text-amber-300" data-testid="run-v2-login-error">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="lab-btn rounded-md px-3 py-2 text-sm"
              onClick={onClose}
            >
              Annulla
            </button>
            <button
              type="submit"
              className="lab-btn rounded-md px-3 py-2 text-sm font-semibold"
              data-testid="run-v2-login-submit"
              disabled={busy}
            >
              {busy ? 'Verifica…' : 'Accedi'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
