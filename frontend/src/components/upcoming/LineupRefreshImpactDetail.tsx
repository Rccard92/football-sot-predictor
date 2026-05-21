import type { LineupRefreshImpactPayload } from '../../lib/api'
import { formatNum } from './format'
import {
  IMPACT_DIRECTION_NOTE,
  formatImpactDelta,
  impactBadgeClass,
} from '../../utils/lineupRefreshImpactDisplay'

function SideRow({
  label,
  before,
  after,
  direction,
  delta,
}: {
  label: string
  before: number | null | undefined
  after: number | null | undefined
  direction: string | null | undefined
  delta: number | null | undefined
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2">
      <span className="text-xs font-medium text-slate-700">{label}</span>
      <div className="flex flex-wrap items-center gap-2 text-xs tabular-nums">
        <span className="text-slate-600">
          {before != null ? formatNum(before) : '—'} → {after != null ? formatNum(after) : '—'}
        </span>
        <span
          className={`rounded-full border px-2 py-0.5 font-semibold ${impactBadgeClass(direction)}`}
        >
          {formatImpactDelta(direction, delta)}
        </span>
      </div>
    </div>
  )
}

export function LineupRefreshImpactDetail({ impact }: { impact?: LineupRefreshImpactPayload | null }) {
  if (!impact?.has_comparison) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/50 px-3 py-2 text-[11px] text-slate-600">
        Nessun confronto disponibile. Usa «Aggiorna formazione SportAPI» per vedere se il pronostico è salito o
        sceso dopo l&apos;ultimo refresh.
      </div>
    )
  }

  const reasons = (impact.reasons ?? []).slice(0, 5)

  return (
    <div className="space-y-3">
      <p className="text-[10px] text-slate-500">{IMPACT_DIRECTION_NOTE}</p>
      <SideRow
        label="Casa"
        before={impact.before_home_sot}
        after={impact.after_home_sot}
        direction={impact.direction_home}
        delta={impact.delta_home_sot}
      />
      <SideRow
        label="Trasferta"
        before={impact.before_away_sot}
        after={impact.after_away_sot}
        direction={impact.direction_away}
        delta={impact.delta_away_sot}
      />
      <SideRow
        label="Totale SOT"
        before={impact.before_total_sot}
        after={impact.after_total_sot}
        direction={impact.direction_total}
        delta={impact.delta_total_sot}
      />
      {reasons.length > 0 ? (
        <div>
          <p className="text-[11px] font-semibold text-slate-800">Motivi principali</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5 text-[11px] text-slate-700">
            {reasons.map((r, i) => (
              <li key={i}>{r.text}</li>
            ))}
          </ul>
        </div>
      ) : impact.main_reason ? (
        <p className="text-[11px] text-slate-700">{impact.main_reason}</p>
      ) : null}
    </div>
  )
}
