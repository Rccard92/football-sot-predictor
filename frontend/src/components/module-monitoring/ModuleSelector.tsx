import { MONITORING_MODULES, type MonitoringModuleKey } from './moduleMonitoringRegistry'
import { ACCENT_CLASSES } from './moduleMonitoringUi'

type Props = {
  active: MonitoringModuleKey
  onSelect: (key: MonitoringModuleKey) => void
}

export function ModuleSelector({ active, onSelect }: Props) {
  return (
    <div
      className="flex gap-2 overflow-x-auto pb-1"
      role="tablist"
      aria-label="Seleziona modulo"
    >
      {MONITORING_MODULES.map((m) => {
        const isActive = m.key === active
        const accent = ACCENT_CLASSES[m.accent]
        return (
          <button
            key={m.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onSelect(m.key)}
            className={`min-w-[9.5rem] shrink-0 rounded-2xl border px-3 py-2.5 text-left transition ${
              isActive
                ? `${accent.border} ${accent.softBg} ring-2 ${accent.ring}`
                : 'border-slate-200/70 bg-white hover:bg-slate-50'
            }`}
          >
            <div className="text-sm font-semibold text-slate-900">{m.shortLabel}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">{m.operationalStatus}</div>
          </button>
        )
      })}
    </div>
  )
}
