import { CARD_BASE } from './moduleMonitoringUi'

type Props = {
  title: string
  reason?: string
  nextAction?: string
  onRefresh?: () => void
  children?: React.ReactNode
}

export function MonitoringEmptyState({
  title,
  reason,
  nextAction,
  onRefresh,
  children,
}: Props) {
  return (
    <div className={`${CARD_BASE} px-5 py-8 text-center`}>
      <h3 className="text-base font-semibold text-slate-800">{title}</h3>
      {reason ? <p className="mx-auto mt-2 max-w-xl text-sm text-slate-600">{reason}</p> : null}
      {nextAction ? <p className="mt-2 text-sm text-slate-500">{nextAction}</p> : null}
      {children}
      {onRefresh ? (
        <button
          type="button"
          onClick={onRefresh}
          className="mt-4 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Aggiorna
        </button>
      ) : null}
    </div>
  )
}
