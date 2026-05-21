import type { OverallXiBreakdown } from '../../utils/lineupOverallXi'

function ScoreRow({
  label,
  value,
  partial,
}: {
  label: string
  value: number | null
  partial?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-[11px]">
      <span className="text-slate-600">{label}</span>
      <span
        className={`font-semibold tabular-nums ${partial && value == null ? 'text-amber-700' : 'text-slate-900'}`}
        title={partial && value == null ? 'Dato parziale' : undefined}
      >
        {value != null ? `${value}` : '—'}
      </span>
    </div>
  )
}

export function SportApiOverallXiCard({ breakdown }: { breakdown: OverallXiBreakdown }) {
  return (
    <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs font-semibold text-indigo-950">Overall XI</p>
        <p className="text-2xl font-bold tabular-nums tracking-tight text-indigo-900">
          {breakdown.overall != null ? `${breakdown.overall}` : '—'}
          <span className="text-sm font-medium text-indigo-700">/100</span>
        </p>
      </div>
      {breakdown.partial_note ? (
        <p className="mt-1 text-[10px] text-amber-800">{breakdown.partial_note}</p>
      ) : null}
      <div className="mt-3 space-y-1 border-t border-indigo-100/80 pt-2">
        <ScoreRow label="Forza offensiva SOT" value={breakdown.attacking_sot_score} partial={breakdown.partial} />
        <ScoreRow label="Solidità difensiva" value={breakdown.defensive_stability_score} partial={breakdown.partial} />
        <ScoreRow label="Equilibrio formazione" value={breakdown.lineup_balance_score} partial={breakdown.partial} />
        <ScoreRow label="Affidabilità dato" value={breakdown.data_confidence_score} partial={breakdown.partial} />
      </div>
    </div>
  )
}
