import type { CecchinoLabAnalyticsOverview } from '../../../lib/cecchinoLabApi'
import { MetricTooltip } from './MetricTooltip'
import { formatNum, formatPct, formatRoi, overviewColors, roiColor } from './overviewTheme'

type Props = {
  goals: CecchinoLabAnalyticsOverview['goals']
  firstHalf: CecchinoLabAnalyticsOverview['first_half']
}

function ProgressRing({ pct, color, label }: { pct: number | null; color: string; label: string }) {
  const v = pct ?? 0
  const r = 28
  const c = 2 * Math.PI * r
  const offset = c * (1 - Math.min(100, Math.max(0, v)) / 100)
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(120,190,220,0.12)" strokeWidth="6" />
        <circle
          cx="36"
          cy="36"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeDasharray={c}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 36 36)"
        />
        <text x="36" y="40" textAnchor="middle" fill="var(--lab-text)" fontSize="12" fontWeight="600">
          {formatPct(pct, 0)}
        </text>
      </svg>
      <span className="text-[11px]" style={{ color: 'var(--lab-muted)' }}>
        {label}
      </span>
    </div>
  )
}

export function GoalLandscape({ goals, firstHalf }: Props) {
  const cards = [
    { label: 'Over 1.5', m: goals.over_15, color: overviewColors.over },
    { label: 'Over 2.5', m: goals.over_25, color: overviewColors.over, roi: true },
    { label: 'Under 2.5', m: goals.under_25, color: overviewColors.under, roi: true },
    { label: 'Under 3.5', m: goals.under_35, color: overviewColors.under },
    { label: 'BTTS sì', m: goals.btts_yes, color: overviewColors.home },
    { label: '0-0', m: goals.score_0_0, color: overviewColors.draw },
  ]

  return (
    <section
      className="rounded-2xl p-4 sm:p-5"
      style={{
        background: 'linear-gradient(160deg, rgba(21,38,58,0.95), rgba(12,24,38,0.98))',
        border: '1px solid var(--lab-border)',
      }}
    >
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lab-cyan)' }}>
        Goal Landscape
      </h2>
      <div className="mb-5 flex flex-wrap justify-around gap-4">
        {cards.slice(0, 4).map((c) => (
          <ProgressRing key={c.label} pct={c.m.percentage} color={c.color} label={c.label} />
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => (
          <div
            key={c.label}
            className="rounded-xl px-3 py-2"
            style={{ background: 'rgba(0,0,0,0.16)', border: '1px solid var(--lab-border)' }}
          >
            <div className="flex items-center justify-between text-sm">
              <span>{c.label}</span>
              <span className="font-semibold tabular-nums" style={{ color: c.color }}>
                {formatPct(c.m.percentage)}
              </span>
            </div>
            <div className="mt-0.5 text-xs" style={{ color: 'var(--lab-muted)' }}>
              {c.m.count.toLocaleString('it-IT')} / {c.m.denominator.toLocaleString('it-IT')}
              {'roi' in c && c.roi ? (
                <>
                  {' · '}
                  <MetricTooltip metric="roi_flat">
                    <span style={{ color: roiColor(c.m.flat_roi_pct) }}>ROI {formatRoi(c.m.flat_roi_pct)}</span>
                  </MetricTooltip>
                  {c.m.average_bet365_pre_odds != null ? ` · q ${formatNum(c.m.average_bet365_pre_odds)}` : null}
                </>
              ) : null}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-3 text-xs" style={{ color: 'var(--lab-muted)' }}>
        <div>Pareggio PT: {formatPct(firstHalf.draw.percentage)}</div>
        <div>Media goal PT: {formatNum(firstHalf.average_goals)}</div>
        <div>% goal nel PT: {formatPct(firstHalf.pct_of_ft_goals)}</div>
      </div>
    </section>
  )
}
