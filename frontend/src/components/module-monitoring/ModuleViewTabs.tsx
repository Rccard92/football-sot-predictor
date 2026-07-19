import type { MonitoringViewDef } from './moduleMonitoringRegistry'

type Props = {
  views: MonitoringViewDef[]
  active: string
  onSelect: (viewId: string) => void
}

export function ModuleViewTabs({ views, active, onSelect }: Props) {
  return (
    <div
      className="flex gap-1 overflow-x-auto rounded-xl border border-slate-200/70 bg-slate-50/80 p-1"
      role="tablist"
      aria-label="Vista modulo"
    >
      {views.map((v) => {
        const isActive = v.id === active
        return (
          <button
            key={v.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onSelect(v.id)}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              isActive
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {v.label}
          </button>
        )
      })}
    </div>
  )
}
