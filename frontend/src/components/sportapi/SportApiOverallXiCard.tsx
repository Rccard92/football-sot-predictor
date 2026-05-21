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

const CONFIDENCE_BADGE: Record<string, string> = {
  alta: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  media: 'border-amber-200 bg-amber-50 text-amber-950',
  bassa: 'border-rose-200 bg-rose-50 text-rose-900',
}

export function SportApiOverallXiCard({ breakdown }: { breakdown: OverallXiBreakdown }) {
  const confClass = CONFIDENCE_BADGE[breakdown.confidence_level] ?? CONFIDENCE_BADGE.media

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
        <ScoreRow label="Attacco SOT" value={breakdown.attacking_sot_score} partial={breakdown.partial} />
        <ScoreRow
          label="Presenza top shooter"
          value={breakdown.offensive_presence_score}
          partial={breakdown.partial}
        />
        <ScoreRow
          label="Solidità difensiva"
          value={breakdown.defensive_stability_score}
          partial={breakdown.partial}
        />
        <ScoreRow label="Continuità XI" value={breakdown.xi_continuity_score} partial={breakdown.partial} />
        <ScoreRow label="Gestione assenze" value={breakdown.availability_score} partial={breakdown.partial} />
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-indigo-100/80 pt-2">
        <span className="text-[11px] text-slate-600">Confidence dato</span>
        <div className="flex items-center gap-2">
          {breakdown.confidence_score != null ? (
            <span className="text-sm font-semibold tabular-nums text-slate-900">
              {breakdown.confidence_score}/100
            </span>
          ) : null}
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize ${confClass}`}>
            {breakdown.confidence_level}
          </span>
        </div>
      </div>

      {breakdown.explanation_bullets.length > 0 ? (
        <ul className="mt-3 list-inside list-disc space-y-0.5 border-t border-indigo-100/80 pt-2 text-[10px] leading-relaxed text-slate-700">
          {breakdown.explanation_bullets.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
