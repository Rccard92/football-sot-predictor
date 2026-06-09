import type { SignalsBucket } from '../../../lib/cecchinoSignalsApi'
import { formatOdds, formatTakenProfit } from './signalsHeatmapUtils'

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

function formatAvgSignalsPerFixture(value: number | null | undefined): string {
  if (value == null) return '—'
  return value.toFixed(1)
}

function formatSuccessRate(rate: number | null | undefined): string {
  if (rate == null) return '—'
  return `${rate.toFixed(1)}%`
}

export function SignalsMonitoringKpiCards({ overall }: Props) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {cards.map((card) => (
          <div key={card.key} className="rounded-lg border border-slate-200 bg-white px-3 py-3">
            <p className="text-xs text-slate-500">{card.label}</p>
            <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
              {overall[card.key] ?? 0}
            </p>
          </div>
        ))}
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-3">
          <p className="text-xs text-slate-500">Media segnali / partita</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
            {formatAvgSignalsPerFixture(overall.avg_signals_per_fixture)}
          </p>
          <p className="mt-1 text-[10px] text-slate-500">su partite eleggibili</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 col-span-2 md:col-span-4">
          <p className="text-xs text-slate-500">Success rate (won / settled)</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
            {formatSuccessRate(overall.success_rate)}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-teal-200 bg-teal-50/60 px-3 py-3">
          <p className="text-xs text-teal-800">Quota media prese</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
            {formatOdds(overall.avg_won_book_odds)}
          </p>
          <p className="mt-1 text-[10px] text-teal-700">solo segnali vinti</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-3">
          <p className="text-xs text-slate-500">Quota Void</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
            {formatOdds(overall.quota_void)}
          </p>
          <p className="mt-1 text-[10px] text-slate-500">soglia pareggio</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-3">
          <p className="text-xs text-slate-500">Margine Void</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
            {overall.void_margin != null
              ? `${overall.void_margin > 0 ? '+' : ''}${overall.void_margin.toFixed(2)}`
              : '—'}
          </p>
          <p className="mt-1 text-[10px] text-slate-500">quota prese − quota void</p>
        </div>
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 px-3 py-3">
          <p className="text-xs text-emerald-800">Rendimento prese</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
            {formatTakenProfit(overall.taken_profit_indicator)}
          </p>
          <p className="mt-1 text-[10px] text-emerald-700">WR × quota prese − 1</p>
        </div>
      </div>
    </div>
  )
}
