import type { CecchinoLabAnalyticsOverview } from '../../../lib/cecchinoLabApi'
import { MetricTooltip } from './MetricTooltip'
import { formatNum, formatPct, formatRoi, overviewColors, roiColor } from './overviewTheme'

type Props = { outcomes: CecchinoLabAnalyticsOverview['outcomes_1x2'] }

export function Outcomes1x2({ outcomes }: Props) {
  const items = [
    { key: 'home', label: '1 Casa', color: overviewColors.home, data: outcomes.home },
    { key: 'draw', label: 'X Pareggio', color: overviewColors.draw, data: outcomes.draw },
    { key: 'away', label: '2 Trasferta', color: overviewColors.away, data: outcomes.away },
  ] as const
  const total = items.reduce((s, i) => s + i.data.count, 0)

  return (
    <section
      className="rounded-2xl p-4 sm:p-5"
      style={{
        background: 'linear-gradient(160deg, rgba(21,38,58,0.95), rgba(15,28,44,0.98))',
        border: '1px solid var(--lab-border)',
      }}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lab-cyan)' }}>
          Esiti 1 / X / 2
        </h2>
        <span className="text-xs" style={{ color: 'var(--lab-muted)' }}>
          <MetricTooltip metric="roi_flat">ROI storico flat 1u — non è una strategia di gioco</MetricTooltip>
        </span>
      </div>

      <div className="mb-4 flex h-4 w-full overflow-hidden rounded-full" style={{ background: 'rgba(0,0,0,0.25)' }}>
        {items.map((i) => {
          const w = total > 0 ? (100 * i.data.count) / total : 0
          return (
            <div
              key={i.key}
              style={{ width: `${w}%`, background: i.color, opacity: 0.85 }}
              title={`${i.label}: ${formatPct(i.data.percentage)}`}
            />
          )
        })}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {items.map((i) => (
          <div
            key={i.key}
            className="rounded-xl p-3"
            style={{ background: 'rgba(0,0,0,0.18)', border: `1px solid ${i.color}33` }}
          >
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: i.color }} />
              <span className="text-sm font-medium">{i.label}</span>
            </div>
            <div className="mt-2 text-2xl font-semibold tabular-nums" style={{ color: i.color }}>
              {formatPct(i.data.percentage)}
            </div>
            <div className="mt-1 space-y-0.5 text-xs" style={{ color: 'var(--lab-muted)' }}>
              <div>{i.data.count.toLocaleString('it-IT')} partite</div>
              <div>
                <MetricTooltip metric="pre_closing">Quota media</MetricTooltip>: {formatNum(i.data.average_bet365_pre_odds)}
              </div>
              <div style={{ color: roiColor(i.data.flat_roi_pct) }}>
                ROI flat {formatRoi(i.data.flat_roi_pct)} · P/L {formatNum(i.data.flat_profit_units, 1)} u
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
