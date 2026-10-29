import { useAuth } from '../../contexts/AuthContext'
import { LoginForm } from './LoginForm'

/** Pagina di accesso: con la protezione attiva, chi non ha una sessione vede solo questa. */
export function LoginPage() {
  const { refresh } = useAuth()
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F6F7F9] px-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">SOT Predictor</p>
        <h1 className="mt-1 text-xl font-semibold text-slate-900">Accedi al Cecchino</h1>
        <p className="mt-1 text-sm text-slate-500">Usa l&apos;email e la password che ti ha mandato l&apos;amministratore.</p>
        <div className="mt-5">
          <LoginForm onSuccess={refresh} />
        </div>
      </div>
    </div>
  )
}
