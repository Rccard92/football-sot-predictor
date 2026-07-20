import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import {
  getMonitoringModule,
  type MonitoringModuleKey,
} from './moduleMonitoringRegistry'
import {
  dataCoverageLabel,
  operationalStatusLabel,
  scientificMaturityLabel,
} from './moduleMonitoringUi'

type Props = {
  item: ModuleOverviewItem
  compact?: boolean
}

export function ModuleCardSections({ item, compact = false }: Props) {
  const def = getMonitoringModule(item.module_key as MonitoringModuleKey)
  const operational = operationalStatusLabel(item.status, def.operationalStatus)
  const coverage = dataCoverageLabel(item)
  const maturity = scientificMaturityLabel(item.scientific_maturity, item.module_key)

  if (compact) {
    return (
      <div className="mt-2 space-y-1 text-xs text-slate-600">
        <p>
          <span className="font-semibold text-slate-500">Operativo:</span> {operational}
        </p>
        <p>
          <span className="font-semibold text-slate-500">Copertura:</span> {coverage}
        </p>
        <p>
          <span className="font-semibold text-slate-500">Maturità:</span> {maturity}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <section>
        <h4 className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
          Stato operativo
        </h4>
        <p className="mt-0.5 text-sm font-medium text-slate-800">{operational}</p>
      </section>
      <section>
        <h4 className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
          Copertura dati
        </h4>
        <p className="mt-0.5 text-sm font-medium text-slate-800">{coverage}</p>
      </section>
      <section>
        <h4 className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
          Maturità scientifica
        </h4>
        <p className="mt-0.5 text-sm font-medium text-slate-800">{maturity}</p>
      </section>
    </div>
  )
}
