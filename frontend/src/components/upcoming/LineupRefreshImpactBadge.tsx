import type { LineupRefreshImpactPayload } from '../../lib/api'
import {
  IMPACT_DIRECTION_NOTE,
  formatImpactDelta,
  impactBadgeClass,
} from '../../utils/lineupRefreshImpactDisplay'

export function LineupRefreshImpactBadge({
  impact,
  showReason = false,
  compact = false,
}: {
  impact?: LineupRefreshImpactPayload | null
  showReason?: boolean
  compact?: boolean
}) {
  if (!impact?.has_comparison) {
    return (
      <span
        className="text-[11px] text-slate-500"
        title="Nessun confronto disponibile. Aggiorna le formazioni per calcolare la variazione."
      >
        —
      </span>
    )
  }

  const dir = impact.direction_total
  const delta = impact.delta_total_sot
  const title = [formatImpactDelta(dir, delta), impact.main_reason, IMPACT_DIRECTION_NOTE]
    .filter(Boolean)
    .join('\n')

  return (
    <div className={compact ? 'space-y-0.5' : 'space-y-1'} title={title}>
      <span
        className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold tabular-nums ${impactBadgeClass(dir)}`}
      >
        {formatImpactDelta(dir, delta)}
      </span>
      {showReason && impact.main_reason ? (
        <p className="max-w-[14rem] text-[10px] leading-snug text-slate-600">{impact.main_reason}</p>
      ) : null}
    </div>
  )
}
