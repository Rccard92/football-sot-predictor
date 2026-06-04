import type { CecchinoFinalOdds } from '../../lib/api'

type Props = {
  final: CecchinoFinalOdds
}

function cell(label: string, quota: number | null, probPct: number | null) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-center">
      <p className="text-[11px] font-semibold uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-900 tabular-nums">
        {quota != null ? quota.toFixed(2) : '—'}
      </p>
      <p className="text-xs text-slate-600 tabular-nums">
        {probPct != null ? `${probPct.toFixed(2)}%` : '—'}
      </p>
    </div>
  )
}

export function CecchinoFinalOddsCard({ final }: Props) {
  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/40 p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-indigo-900">Quota matematica finale Cecchino</h3>
        <span className="text-[10px] uppercase text-indigo-700">{final.status}</span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {cell('1', final.quota_1, final.prob_1_pct)}
        {cell('X', final.quota_x, final.prob_x_pct)}
        {cell('2', final.quota_2, final.prob_2_pct)}
      </div>
      <p className="mt-3 text-[11px] text-slate-600">
        Pesi: casa/trasferta 20% · totali 25% · ultime 5 20% · ultime 6 35%
      </p>
    </div>
  )
}
