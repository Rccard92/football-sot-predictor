import type { SignalsBucket } from '../../../lib/cecchinoSignalsApi'
import { formatSuccessRate } from './signalsHeatmapUtils'

type Props = {
  overall: SignalsBucket
}

const cards: Array<{ key: keyof SignalsBucket; label: string }> = [
  { key: 'activations', label: 'Segnali accesi' },
  { key: 'settled', label: 'Valutati' },
  { key: 'won', label: 'Vinti' },
  { key: 'lost', label: 'Persi' },
  { key: 'pending', label: 'Pending' },
  { key: 'not_evaluable', label: 'Non valutabili' },
]

export function SignalsMonitoringKpiCards({ overall }: Props) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
      {cards.map((card) => (
        <div key={card.key} className="rounded-lg border border-slate-200 bg-white px-3 py-3">
          <p className="text-xs text-slate-500">{card.label}</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
            {overall[card.key] ?? 0}
          </p>
        </div>
      ))}
      <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 col-span-2 md:col-span-4 xl:col-span-7">
        <p className="text-xs text-slate-500">Success rate (won / settled)</p>
        <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
          {formatSuccessRate(overall.success_rate)}
        </p>
      </div>
    </div>
  )
}
