import { todaySkeleton } from '../cecchino/cecchinoTodayStyles'

export function V4Loading({ label = 'Caricamento…', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite" data-testid="v4-loading">
      <p className="text-base text-slate-500">{label}</p>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className={`${todaySkeleton} h-16 w-full`} />
      ))}
    </div>
  )
}

export function V4Error({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-base text-red-800"
      role="alert"
      data-testid="v4-error"
    >
      <span>{message}</span>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-base font-medium text-red-800 hover:bg-red-100"
        >
          Riprova
        </button>
      ) : null}
    </div>
  )
}

export function V4Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div
      className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center"
      data-testid="v4-empty"
    >
      <p className="text-base font-semibold text-slate-700">{title}</p>
      {hint ? <p className="mt-1 text-base text-slate-500">{hint}</p> : null}
    </div>
  )
}
