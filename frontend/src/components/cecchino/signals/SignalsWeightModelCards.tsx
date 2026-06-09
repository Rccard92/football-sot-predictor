import type { WeightModelSummary } from '../../../lib/cecchinoSignalsApi'
import { formatOdds, formatTakenProfit } from './signalsHeatmapUtils'

type Props = {
  models: WeightModelSummary[]
  selectedModelKey: string
  loading?: boolean
  onSelect: (modelKey: string) => void
}

function formatWinRate(rate: number | null | undefined): string {
  if (rate == null) return '—'
  return `${rate.toFixed(1)}%`
}

export function SignalsWeightModelCards({ models, selectedModelKey, loading, onSelect }: Props) {
  if (loading && models.length === 0) {
    return <p className="text-sm text-slate-500">Caricamento modelli...</p>
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {models.map((model) => {
        const selected = model.model_key === selectedModelKey
        const notCalculated = model.activations === 0
        return (
          <button
            key={model.model_key}
            type="button"
            onClick={() => onSelect(model.model_key)}
            className={`rounded-lg border px-3 py-3 text-left transition-colors ${
              selected
                ? 'border-violet-500 bg-violet-50 ring-2 ring-violet-300'
                : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
            }`}
          >
            {notCalculated ? (
              <>
                <p className="text-sm font-semibold text-slate-800">{model.short_label}</p>
                <p className="mt-2 text-lg font-semibold text-slate-400">Non calcolato</p>
                <p className="mt-2 text-xs text-slate-500">{model.weights}</p>
              </>
            ) : (
              <>
                <p className="text-2xl font-bold tabular-nums text-slate-900">
                  {formatWinRate(model.win_rate)}
                </p>
                <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
                  Win Rate
                </p>
                <p className="mt-2 text-sm font-semibold text-slate-800">{model.short_label}</p>
                <p className="mt-1 text-xs text-slate-500">{model.weights}</p>
                <div className="mt-2 space-y-0.5 text-[11px] text-slate-600">
                  <p>Segnali accesi: {model.activations}</p>
                  <p>Quota prese: {formatOdds(model.avg_won_book_odds)}</p>
                  <p>Quota void: {formatOdds(model.quota_void)}</p>
                  <p className="font-medium text-emerald-800">
                    Rendimento: {formatTakenProfit(model.taken_profit_indicator)}
                  </p>
                </div>
              </>
            )}
          </button>
        )
      })}
    </div>
  )
}
