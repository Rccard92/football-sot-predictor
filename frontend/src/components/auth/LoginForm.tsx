import { useState } from 'react'
import { AdminHttpError } from '../../lib/api'
import { login } from '../../lib/authApi'

const inputClass =
  'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none'

/** Form email + password; la password resta nello stato solo per il tempo della richiesta. */
export function LoginForm({ onSuccess }: { onSuccess: () => void | Promise<void> }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!email.trim() || !password) {
      setError('Inserisci email e password.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
      setPassword('')
      await onSuccess()
    } catch (e) {
      if (e instanceof AdminHttpError && e.status === 429) setError(e.message || 'Troppi tentativi: riprova tra qualche minuto.')
      else if (e instanceof AdminHttpError && (e.status === 401 || e.status === 403)) setError(e.message)
      else setError('Accesso non riuscito: riprova tra poco.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault()
        void submit()
      }}
    >
      <label className="block">
        <span className="text-[13px] font-medium text-slate-600">Email</span>
        <input
          type="email"
          autoComplete="username"
          className={`mt-1 ${inputClass}`}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoFocus
        />
      </label>
      <label className="block">
        <span className="text-[13px] font-medium text-slate-600">Password</span>
        <input
          type="password"
          autoComplete="current-password"
          className={`mt-1 ${inputClass}`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      <button
        type="submit"
        className="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
        disabled={busy}
      >
        {busy ? 'Accesso…' : 'Accedi'}
      </button>
    </form>
  )
}
