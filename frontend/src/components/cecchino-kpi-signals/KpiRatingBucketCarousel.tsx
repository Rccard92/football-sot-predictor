import { motion } from 'framer-motion'
import type { KpiSignalsBucket } from '../../lib/cecchinoKpiSignalsApi'
import { KPI_RATING_BUCKETS } from '../../lib/cecchinoKpiSignalsApi'

type Props = {
  buckets: Array<KpiSignalsBucket & { rating_bucket: string }>
  selectedBucket: string
  onSelect: (bucket: string) => void
}

export function KpiRatingBucketCarousel({ buckets, selectedBucket, onSelect }: Props) {
  const byKey = Object.fromEntries(buckets.map((b) => [b.rating_bucket, b]))
  return (
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {KPI_RATING_BUCKETS.map((bucket) => {
        const data = byKey[bucket]
        const active = selectedBucket === bucket
        return (
          <motion.button
            key={bucket}
            type="button"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => onSelect(active ? '' : bucket)}
            className={`rounded-2xl border p-4 text-left shadow-sm transition ${
              active ? 'border-cyan-500 bg-cyan-50 ring-2 ring-cyan-200' : 'border-slate-200 bg-white hover:border-cyan-200'
            }`}
          >
            <p className="text-xs font-semibold uppercase text-slate-500">Rating</p>
            <p className="text-lg font-bold text-slate-900">{bucket}</p>
            <div className="mt-2 space-y-1 text-xs text-slate-600">
              <p>Win rate: {data?.win_rate != null ? `${data.win_rate}%` : '—'}</p>
              <p>Profitto: {data?.profit_units != null ? data.profit_units.toFixed(2) : '—'}</p>
              <p>ROI: {data?.roi_pct != null ? `${data.roi_pct}%` : '—'}</p>
              <p>Valutati: {data?.settled ?? 0}</p>
            </div>
          </motion.button>
        )
      })}
    </section>
  )
}
