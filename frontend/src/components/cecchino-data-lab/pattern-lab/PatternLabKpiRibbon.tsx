import { motion } from 'framer-motion'
import { formatNum, formatPct, type PatternLabSummary } from '../../../lib/patternLabApi'
import { roiColor } from '../overview/overviewTheme'

type Props = {
  summary: PatternLabSummary
  marketInformativeDefault?: boolean
}

function PulseKpi({
  label,
  value,
  color,
}: {
  label: string
  value: string
  color?: string
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
        style={{
          background: `radial-gradient(circle, ${color || 'var(--lab-cyan)'} 0%, transparent 70%)`,
        }}
      />
      <div className="text-[11px] uppercase tracking-wider" style={{ color: 'var(--lab-muted)' }}>
        {label}
      </div>
      <div
        className="mt-2 text-2xl font-semibold tabular-nums tracking-tight"
        style={{ color: color || 'var(--lab-text)' }}
      >
        {value}
      </div>
    </motion.div>
  )
}

export function PatternLabKpiRibbon({ summary, marketInformativeDefault = true }: Props) {
  const historical =
    summary.selections_historical_total != null
      ? String(summary.selections_historical_total)
      : '—'
  const evidenceLabel = marketInformativeDefault
    ? 'Mercati con evidenza'
    : 'Mercati (universo mostrato)'

  return (
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
      <PulseKpi label={evidenceLabel} value={String(summary.selections)} />
      <PulseKpi label="Mercati storici totali" value={historical} />
      <PulseKpi
        label="Win Rate"
        value={formatPct(summary.win_rate)}
        color={
          summary.win_rate == null
            ? undefined
            : summary.win_rate >= 0.5
              ? 'var(--lab-ok)'
              : 'var(--lab-err)'
        }
      />
      <PulseKpi label="ROI" value={formatPct(summary.roi)} color={roiColor(summary.roi)} />
      <PulseKpi
        label="Profitto 1u"
        value={formatNum(summary.profit_1u)}
        color={roiColor(summary.profit_1u)}
      />
      <PulseKpi label="Quota media" value={formatNum(summary.avg_quota)} />
      <PulseKpi label="Rating medio" value={formatNum(summary.avg_rating ?? null, 1)} />
      <PulseKpi
        label="Acquistabilità V3.6 media"
        value={formatNum(summary.avg_purchasability_v36 ?? null, 1)}
      />
    </section>
  )
}
