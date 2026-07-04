import { motion } from 'framer-motion'
import type { KpiSignalsBucket } from '../../lib/cecchinoKpiSignalsApi'
import { formatOdds } from '../cecchino-lab/signalsLabUtils'
import { formatKpiProfit, formatKpiRoi, formatKpiWinRate, profitTextClass } from './kpiSignalsLabUtils'

type Props = { overall: KpiSignalsBucket }

const METRICS: Array<{
  key: keyof KpiSignalsBucket
  label: string
  format?: (v: unknown) => string
  valueClass?: (v: unknown) => string
}> = [
  { key: 'activations', label: 'Segnali KPI' },
  { key: 'settled', label: 'Valutati' },
  { key: 'won', label: 'Vinti' },
  { key: 'lost', label: 'Persi' },
  { key: 'win_rate', label: 'Win Rate', format: (v) => formatKpiWinRate(v as number | null) },
  { key: 'avg_book_odds_all', label: 'Quota media giocata', format: (v) => formatOdds(v as number | null) },
  { key: 'avg_book_odds_won', label: 'Quota media presa', format: (v) => formatOdds(v as number | null) },
  { key: 'quota_void', label: 'Quota void', format: (v) => formatOdds(v as number | null) },
  {
    key: 'profit_units',
    label: 'Profitto unità',
    format: (v) => formatKpiProfit(v as number | null),
    valueClass: (v) => profitTextClass(v as number | null),
  },
  {
    key: 'roi_pct',
    label: 'ROI %',
    format: (v) => formatKpiRoi(v as number | null),
    valueClass: (v) => profitTextClass(v as number | null),
  },
]

export function KpiSignalsMetricRibbon({ overall }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
      >
        {METRICS.map(({ key, label, format, valueClass }) => {
          const raw = overall[key]
          const display = format != null ? format(raw) : raw != null ? String(raw) : '—'
          const cls = valueClass?.(raw) ?? 'text-slate-900'
          return (
            <div
              key={key}
              className="rounded-xl border border-slate-100 bg-gradient-to-br from-white to-slate-50/80 px-3 py-3 shadow-sm transition hover:shadow-md"
            >
              <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
              <p className={`mt-1 text-xl font-semibold tabular-nums ${cls}`}>{display}</p>
            </div>
          )
        })}
      </motion.div>
    </section>
  )
}
