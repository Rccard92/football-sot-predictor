import type { BalanceReadinessHistory } from '../../../lib/cecchinoModuleMonitoringApi'
import { balanceDecisionLabelIt, CARD_BASE, scientificStatusLabelIt } from '../moduleMonitoringUi'

type Props = {
  history: BalanceReadinessHistory | null
}

export function BalanceReadinessHistoryChart({ history }: Props) {
  const items = history?.items || []

  if (items.length === 0) {
    return (
      <div className={`${CARD_BASE} p-4`}>
        <h4 className="text-sm font-semibold text-slate-800">Storico readiness</h4>
        <p className="mt-2 text-sm text-slate-600">
          Nessuno snapshot giornaliero ancora disponibile.
        </p>
      </div>
    )
  }

  const maxSettled = Math.max(...items.map((e) => e.prospective_settled ?? 0), 1)

  return (
    <div className={`${CARD_BASE} p-4`}>
      <h4 className="text-sm font-semibold text-slate-800">Storico readiness</h4>
      <p className="mt-1 text-xs text-slate-500">
        Snapshot giornalieri — settled prospettici e decisione (nessuno score aggregato)
      </p>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-slate-200 text-slate-500">
            <tr>
              <th className="pb-2 pr-4">Data</th>
              <th className="pb-2 pr-4">Settled</th>
              <th className="pb-2 pr-4">Giorni</th>
              <th className="pb-2 pr-4">Fold</th>
              <th className="pb-2 pr-4">Maturità</th>
              <th className="pb-2 pr-4">Decisione</th>
              <th className="pb-2">Trend settled</th>
            </tr>
          </thead>
          <tbody className="text-slate-700">
            {items.map((entry) => {
              const settled = entry.prospective_settled ?? 0
              const width = Math.round((settled / maxSettled) * 100)
              return (
                <tr key={entry.snapshot_date} className="border-b border-slate-100 last:border-0">
                  <td className="py-2 pr-4 text-slate-600">{entry.snapshot_date}</td>
                  <td className="py-2 pr-4 tabular-nums">{settled}</td>
                  <td className="py-2 pr-4 tabular-nums">{entry.prospective_days ?? '—'}</td>
                  <td className="py-2 pr-4 tabular-nums">{entry.temporal_folds ?? '—'}</td>
                  <td className="py-2 pr-4">
                    {scientificStatusLabelIt(entry.scientific_maturity)}
                  </td>
                  <td className="py-2 pr-4">
                    {balanceDecisionLabelIt(entry.current_decision)}
                  </td>
                  <td className="py-2">
                    <div className="h-2 w-20 overflow-hidden rounded-full bg-slate-200">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-violet-600 to-blue-500"
                        style={{ width: `${width}%` }}
                      />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
