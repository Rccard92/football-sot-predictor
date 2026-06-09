import { memo } from 'react'
import { motion } from 'framer-motion'
import type { WeightModelSummary } from '../../lib/cecchinoSignalsApi'
import {
  formatOdds,
  formatSuccessRate,
  formatTakenProfit,
  MODEL_ACCENT,
} from './signalsLabUtils'

type Props = {
  model: WeightModelSummary
  selected: boolean
  index: number
  onSelect: (key: string) => void
}

export const ModelPerformanceCard = memo(function ModelPerformanceCard({
  model,
  selected,
  index,
  onSelect,
}: Props) {
  const accent = MODEL_ACCENT[model.model_key] ?? MODEL_ACCENT.F
  const notCalculated = model.activations === 0

  return (
    <motion.button
      type="button"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, delay: index * 0.04, ease: 'easeOut' }}
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
      onClick={() => onSelect(model.model_key)}
      className={`relative min-w-[160px] snap-center rounded-2xl border bg-gradient-to-br p-4 text-left transition-shadow duration-200 ${
        selected
          ? `border-transparent ring-2 ${accent.ring} ${accent.bgSelected} shadow-lg ${accent.glow}`
          : `border-slate-200/80 ${accent.bg} shadow-sm hover:shadow-md`
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className={`text-3xl font-bold tabular-nums ${accent.letter}`}>{model.model_key}</span>
        {!notCalculated && (
          <span className={`text-lg font-bold tabular-nums ${accent.text}`}>
            {formatSuccessRate(model.win_rate)}
          </span>
        )}
      </div>
      <p className="mt-1 text-sm font-semibold text-slate-800">{model.short_label}</p>
      <p className="mt-0.5 text-[11px] text-slate-500">{model.weights}</p>

      {notCalculated ? (
        <p className="mt-3 text-sm font-medium text-slate-400">Non calcolato</p>
      ) : (
        <div className="mt-3 space-y-1 text-[11px] text-slate-600">
          <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Win Rate</p>
          <p>Segnali: {model.activations}</p>
          <p>Quota prese: {formatOdds(model.avg_won_book_odds)}</p>
          <p>Quota void: {formatOdds(model.quota_void)}</p>
          <p className={`font-semibold ${accent.text}`}>
            Rendimento: {formatTakenProfit(model.taken_profit_indicator)}
          </p>
        </div>
      )}
    </motion.button>
  )
})
