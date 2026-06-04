type Props = {
  title: string
  message?: string | null
  code?: string | null
  variant?: 'warning' | 'error' | 'info'
}

const VARIANT_CLASS = {
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
  error: 'border-red-200 bg-red-50 text-red-800',
  info: 'border-slate-200 bg-slate-50 text-slate-700',
} as const

export function CecchinoStatusMessage({ title, message, code, variant = 'info' }: Props) {
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${VARIANT_CLASS[variant]}`}>
      <p className="font-semibold">{title}</p>
      {code && <p className="mt-1 text-xs opacity-80">Codice: {code}</p>}
      {message && <p className="mt-1 text-xs">{message}</p>}
    </div>
  )
}
