import type { BalanceTimelineItem } from '../../../lib/cecchinoModuleMonitoringApi'
import { CARD_BASE } from '../moduleMonitoringUi'

type Props = {
  items: BalanceTimelineItem[]
}

export function BalanceReadinessTimeline({ items }: Props) {
  if (!items || items.length === 0) {
    return (
      <div className={`${CARD_BASE} p-4`}>
        <h4 className="text-sm font-semibold text-slate-800">Timeline readiness</h4>
        <p className="mt-2 text-sm text-slate-600">Nessuna milestone configurata.</p>
      </div>
    )
  }

  return (
    <div className={`${CARD_BASE} p-4`}>
      <h4 className="text-sm font-semibold text-slate-800">Timeline readiness</h4>
      <div className="mt-4 space-y-3">
        {items.map((item) => (
          <div key={item.key} className="flex gap-3">
            <div
              className={`flex h-6 w-6 shrink-0 items-center justify-center text-lg ${
                item.done ? 'text-emerald-600' : 'text-slate-400'
              }`}
            >
              {item.done ? '✓' : '○'}
            </div>
            <p className="text-sm font-medium text-slate-800">
              {item.label_it || item.key}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
