import type { ReactNode } from 'react'

type Props = {
  label: string
  value: ReactNode
  hint?: string
}

export function BalanceMetricCard({ label, value, hint }: Props) {
  return (
    <div className="rounded-2xl border border-indigo-100/80 bg-gradient-to-br from-white to-indigo-50/40 p-4 shadow-sm">
      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-900">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  )
}
