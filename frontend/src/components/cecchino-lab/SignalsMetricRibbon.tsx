import { AnimatePresence, motion } from 'framer-motion'
import type { SignalsBucket, WeightModelSummary } from '../../lib/cecchinoSignalsApi'
import { formatOdds, formatTakenProfit, formatVoidMargin, voidMarginClass } from './signalsLabUtils'

type Props = {
  overall: SignalsBucket
  selectedModel: WeightModelSummary | undefined
  modelKey: string
}

const METRICS: Array<{ key: keyof SignalsBucket; label: string; format?: (v: unknown) => string }> = [
  { key: 'activations', label: 'Segnali accesi' },
  { key: 'settled', label: 'Valutati' },
  { key: 'won', label: 'Vinti' },
  { key: 'lost', label: 'Persi' },
  { key: 'pending', label: 'Pending' },
  { key: 'not_evaluable', label: 'Non valutabili' },
  {
    key: 'avg_signals_per_fixture',
    label: 'Media segnali / partita',
    format: (v) => (v == null ? '—' : Number(v).toFixed(1)),
  },
  { key: 'avg_won_book_odds', label: 'Quota media prese', format: (v) => formatOdds(v as number | null) },
  { key: 'quota_void', label: 'Quota Void', format: (v) => formatOdds(v as number | null) },
  {
    key: 'void_margin',
    label: 'Margine Void',
    format: (v) => formatVoidMargin(v as number | null),
  },
  {
    key: 'taken_profit_indicator',
    label: 'Rendimento prese',
    format: (v) => formatTakenProfit(v as number | null),
  },
]

export function SignalsMetricRibbon({ overall, selectedModel, modelKey }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-800">
        Statistiche modello selezionato: {selectedModel?.short_label ?? `Modello ${modelKey}`}
      </h2>
      <AnimatePresence mode="wait">
        <motion.div
          key={modelKey}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2 }}
          className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6"
        >
          {METRICS.map(({ key, label, format }) => {
            const raw = overall[key]
            const display =
              format != null ? format(raw) : raw != null ? String(raw) : '—'
            const isDelta = key === 'void_margin' || key === 'taken_profit_indicator'
            return (
              <div
                key={key}
                className="rounded-xl border border-slate-100 bg-gradient-to-br from-white to-slate-50/80 px-3 py-3 shadow-sm"
              >
                <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
                <p
                  className={`mt-1 text-xl font-semibold tabular-nums ${
                    isDelta && key === 'void_margin'
                      ? voidMarginClass(raw as number | null)
                      :                     isDelta && key === 'taken_profit_indicator'
                        ? voidMarginClass(raw as number | null)
                        : 'text-slate-900'
                  }`}
                >
                  {display}
                </p>
              </div>
            )
          })}
        </motion.div>
      </AnimatePresence>
    </section>
  )
}
