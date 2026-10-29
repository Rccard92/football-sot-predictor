import { useState } from 'react'
import { AdminHttpError } from '../../lib/api'
import { changePassword } from '../../lib/authApi'
import { useAuth } from '../../contexts/AuthContext'

const inputClass =
  'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none'

/** Cambio password. `required`: primo accesso o password reimpostata, il dialogo non si chiude finche'
 *  non si sceglie una password propria; altrimenti e' il cambio volontario dal menu. */
export function ChangePasswordDialog({ required, onClose }: { required: boolean; onClose?: () => void }) {
  const { refresh, logout } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const submit = async () => {
    if (!current || !next) {
      setError('Compila tutti i campi.')
      return
    }
    if (next !== confirm) {
      setError('Le due nuove password non coincidono.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await changePassword(current, next)
      setCurrent('')
      setNext('')
      setConfirm('')
      if (required) await refresh()
      else setDone(true)
    } catch (e) {
      setError(e instanceof AdminHttpError ? e.message : 'Cambio password non riuscito.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Cambia password"
    >
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl">
        <h2 className="text-base font-semibold text-slate-900">
          {required ? 'Scegli la tua password' : 'Cambia password'}
        </h2>
        {done ? (
          <>
            <p className="mt-2 text-sm text-slate-700">Password cambiata. Gli altri dispositivi dovranno rifare l&apos;accesso.</p>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
                onClick={onClose}
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
            {required ? (
              <p className="text-sm text-slate-600">
                Per sicurezza, al primo accesso devi sostituire la password che hai ricevuto con una tua.
              </p>
            ) : null}
            <label className="block">
              <span className="text-[13px] font-medium text-slate-600">
                {required ? 'Password ricevuta' : 'Password attuale'}
              </span>
              <input type="password" autoComplete="current-password" className={inputClass} value={current} onChange={(e) => setCurrent(e.target.value)} autoFocus />
            </label>
            <label className="block">
              <span className="text-[13px] font-medium text-slate-600">Nuova password</span>
              <input type="password" autoComplete="new-password" className={inputClass} value={next} onChange={(e) => setNext(e.target.value)} />
              <span className="mt-1 block text-[13px] text-slate-500">Almeno 10 caratteri, con lettere e numeri.</span>
            </label>
            <label className="block">
              <span className="text-[13px] font-medium text-slate-600">Ripeti la nuova password</span>
              <input type="password" autoComplete="new-password" className={inputClass} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </label>
            {error ? <p className="text-sm text-rose-700">{error}</p> : null}
            <div className="flex justify-end gap-2">
              {required ? (
                <button
                  type="button"
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  onClick={() => void logout()}
                  disabled={busy}
                >
                  Esci
                </button>
              ) : (
                <button
                  type="button"
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  onClick={onClose}
                  disabled={busy}
                >
                  Annulla
                </button>
              )}
              <button
                type="submit"
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
                disabled={busy}
              >
                {busy ? 'Salvo…' : 'Salva password'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
