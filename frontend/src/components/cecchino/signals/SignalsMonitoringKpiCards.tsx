import type { MonitoringVersion, SignalsBucket } from '../../../lib/cecchinoSignalsApi'
import { SIGNAL_FORMULA_CURRENT_BADGE } from '../../../lib/cecchinoSignalsApi'
import { formatOdds, formatTakenProfit } from './signalsHeatmapUtils'

type Props = {
  overall: SignalsBucket
  title?: string
  monitoringVersion?: MonitoringVersion
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

export function SignalsMonitoringKpiCards({ overall, title, monitoringVersion }: Props) {
  const monitoringBadge =
    monitoringVersion === 'v1' ? 'Monitoraggio V1' : monitoringVersion === 'v2' ? 'Monitoraggio V2' : null

  return (
    <div className="space-y-3" data-testid="signals-monitoring-kpi">
      <div className="flex flex-wrap items-center gap-2">
        {title && <h2 className="text-sm font-semibold text-slate-800">{title}</h2>}
        {monitoringBadge && (
          <span
            data-testid="monitoring-version-badge"
            className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium ${
              monitoringVersion === 'v1'
                ? 'border-slate-300 bg-slate-100 text-slate-700'
                : 'border-indigo-300 bg-indigo-50 text-indigo-800'
            }`}
          >
            {monitoringBadge}
          </span>
        )}
        <span
          data-testid="formula-version-badge"
          className="inline-flex rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600"
        >
          {SIGNAL_FORMULA_CURRENT_BADGE}
        </span>
      </div>
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
