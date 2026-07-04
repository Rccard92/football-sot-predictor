import { motion } from 'framer-motion'
import type { KpiSignalsBucket } from '../../lib/cecchinoKpiSignalsApi'
import { KPI_RATING_BUCKETS } from '../../lib/cecchinoKpiSignalsApi'
import {
  bucketAccentClass,
  formatKpiOdds,
  formatKpiProfit,
  formatKpiRoi,
  formatKpiWinRate,
  profitTextClass,
} from './kpiSignalsLabUtils'

type Props = {
  buckets: Array<KpiSignalsBucket & { rating_bucket: string }>
  selectedBucket: string
  onSelect: (bucket: string) => void
  onClearFilter?: () => void
}

export function KpiRatingBucketCarousel({ buckets, selectedBucket, onSelect, onClearFilter }: Props) {
  const byKey = Object.fromEntries(buckets.map((b) => [b.rating_bucket, b]))

  return (
    <section className="space-y-3">
      {selectedBucket ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-cyan-100 px-3 py-1 text-xs font-medium text-cyan-900">
            Filtro attivo: {selectedBucket}
          </span>
          <button
            type="button"
            onClick={() => {
              onSelect('')
              onClearFilter?.()
            }}
            className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
          >
            ✕ Rimuovi
          </button>
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {KPI_RATING_BUCKETS.map((bucket, idx) => {
          const data = byKey[bucket]
          const active = selectedBucket === bucket
          const accent = bucketAccentClass(data)
          const profit = data?.profit_units ?? null

          return (
            <motion.button
              key={bucket}
              type="button"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.04 }}
              whileHover={{ scale: 1.02, y: -2 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => onSelect(active ? '' : bucket)}
              className={`rounded-2xl border bg-gradient-to-br p-4 text-left shadow-sm transition-all duration-200 hover:shadow-md ${accent.card} ${
                active ? 'ring-2 ring-cyan-400/70 ring-offset-1' : accent.glow
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Rating</p>
                {data && data.settled >= 3 && profit != null ? (
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${accent.badge}`}>
                    {profit >= 0 ? '+' : ''}
                    {profit.toFixed(2)}
                  </span>
                ) : data && data.settled > 0 && data.settled < 3 ? (
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                    campione basso
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">{bucket}</p>
              <div className="mt-3 space-y-1 text-xs text-slate-600">
                <p>
                  Win rate:{' '}
                  <span className="font-semibold tabular-nums">{formatKpiWinRate(data?.win_rate)}</span>
                </p>
                <p className={profitTextClass(profit)}>
                  Profitto: <span className="font-semibold tabular-nums">{formatKpiProfit(profit)}</span>
                </p>
                <p>
                  ROI: <span className="font-semibold tabular-nums">{formatKpiRoi(data?.roi_pct)}</span>
                </p>
                <p>
                  Valutati: <span className="font-semibold tabular-nums">{data?.settled ?? 0}</span>
                </p>
                <p>
                  Quota media:{' '}
                  <span className="font-semibold tabular-nums">{formatKpiOdds(data?.avg_book_odds_all)}</span>
                </p>
              </div>
            </motion.button>
          )
        })}
      </div>
    </section>
  )
}
