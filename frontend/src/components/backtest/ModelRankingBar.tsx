import type { RoundAnalysisModelOverviewStats, RoundAnalysisOverview } from '../../lib/api'
import { MODEL_KEYS } from './roundAnalysisUtils'

const KEY_LABEL: Record<string, string> = {
  [MODEL_KEYS.v11]: 'v1.1',
  [MODEL_KEYS.v20]: 'v2.0',
  [MODEL_KEYS.v21]: 'v2.1',
  [MODEL_KEYS.v30]: 'v3.0',
}

function labelFor(key: string | undefined, models: Record<string, RoundAnalysisModelOverviewStats>) {
  if (!key) return '—'
  return models[key]?.label ?? KEY_LABEL[key] ?? key
}

type Props = {
  overview: RoundAnalysisOverview
}

export function ModelRankingBar({ overview }: Props) {
  const { ranking, models } = overview
  if (!ranking || overview.rounds_analyzed === 0) {
    return (
      <p className="text-sm text-slate-500">
        Ranking provvisorio: analizza almeno una giornata per confrontare i modelli.
      </p>
    )
  }

  const items = [
    { label: 'Migliore cauta', key: ranking.best_cautious },
    { label: 'Migliore aggressiva', key: ranking.best_aggressive },
    { label: 'Migliore affidabilità', key: ranking.best_reliability },
    { label: 'Migliore MAE', key: ranking.best_mae },
    { label: 'Bias più basso', key: ranking.best_bias },
  ]

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
      <p className="font-medium text-slate-800">
        Ranking provvisorio sulle {overview.rounds_analyzed} giornate analizzate
      </p>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-700">
        {items.map((item) => (
          <li key={item.label}>
            <span className="text-slate-500">{item.label}:</span>{' '}
            <span className="font-medium">{labelFor(item.key, models)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
