import { motion } from 'framer-motion'
import type { CecchinoLabAnalyticsOverview } from '../../../lib/cecchinoLabApi'
import { MetricTooltip } from './MetricTooltip'
import { formatPct, formatRoi, roiColor } from './overviewTheme'

type Props = { summary: CecchinoLabAnalyticsOverview['summary'] }

function PulseCard({
  label,
  value,
  hint,
  color,
  tooltip,
}: {
  label: string
  value: string
  hint?: string
  color?: string
  tooltip?: string
}) {
  return (
    <motion.div
      className="relative overflow-hidden rounded-2xl p-4"
      style={{
        background: 'linear-gradient(145deg, rgba(26,47,71,0.9) 0%, rgba(18,32,51,0.95) 100%)',
        border: '1px solid var(--lab-border)',
      }}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28 }}
    >
      <div
        className="pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full opacity-30"
        style={{ background: `radial-gradient(circle, ${color || 'var(--lab-cyan)'} 0%, transparent 70%)` }}
      />
      <div className="text-[11px] uppercase tracking-wider" style={{ color: 'var(--lab-muted)' }}>
        {tooltip ? (
          <MetricTooltip metric={tooltip}>{label}</MetricTooltip>
        ) : (
          label
        )}
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums sm:text-3xl" style={{ color: color || 'var(--lab-cyan)' }}>
        {value}
      </div>
      {hint ? (
        <div className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
          {hint}
        </div>
      ) : null}
    </motion.div>
  )
}

export function MarketPulse({ summary }: Props) {
  const best = summary.best_flat_roi
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lab-cyan)' }}>
        Market Pulse
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <PulseCard
          label="Partite analizzate"
          value={summary.matches_total.toLocaleString('it-IT')}
          hint={`${summary.competitions_count} camp. · ${summary.seasons_count} stag.`}
        />
        <PulseCard
          label="Goal medi"
          value={summary.average_goals_per_match?.toFixed(2) ?? '—'}
          hint={`Casa ${summary.average_home_goals?.toFixed(2) ?? '—'} · Trasf. ${summary.average_away_goals?.toFixed(2) ?? '—'}`}
          color="var(--lab-ok)"
        />
        <PulseCard
          label="Favorita vincente"
          value={formatPct(summary.favorite_hit_rate)}
          tooltip="favorite"
          color="var(--lab-warn)"
        />
        <PulseCard
          label="Margine Bet365 medio"
          value={formatPct(summary.average_pre_closing_margin_pct)}
          tooltip="margin"
        />
        <PulseCard
          label="Miglior ROI flat"
          value={best ? formatRoi(best.roi) : '—'}
          hint={best ? best.label : undefined}
          tooltip="roi_flat"
          color={roiColor(best?.roi)}
        />
        <PulseCard
          label="Anomalie dati"
          value={String(summary.anomalies_errors + summary.anomalies_warnings)}
          hint={`${summary.anomalies_errors} err · ${summary.anomalies_warnings} warn · cov. ${formatPct(summary.bet365_1x2_coverage_pct)}`}
          color="var(--lab-err)"
          tooltip="coverage"
        />
      </div>
    </section>
  )
}
