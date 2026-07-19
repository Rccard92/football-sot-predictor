import { MonitoraggioSegnaliLab } from '../../pages/MonitoraggioSegnaliLab'
import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import { MonitoringEmptyState } from './MonitoringEmptyState'
import { MonitoringExportMenu } from './MonitoringExportMenu'
import { MonitoringMetricCard } from './MonitoringMetricCard'
import { monitoringStatusLabel } from './moduleMonitoringUi'

type Props = {
  view: string
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  overview?: ModuleOverviewItem | null
}

export function SignalsModulePanel({
  view,
  dateFrom,
  dateTo,
  competitionId,
  overview,
}: Props) {
  if (view === 'overview' || view === 'performance' || view === 'models' || view === 'trends') {
    const statusRaw = overview?.status || 'operational'
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MonitoringMetricCard
            label="Stato"
            value={monitoringStatusLabel(statusRaw)}
            ariaLabel={`Stato ${statusRaw}`}
          />
          <MonitoringMetricCard label="Versione" value={overview?.version || 'signals_lab'} />
          <MonitoringMetricCard
            label="Fixture"
            value={overview?.fixtures == null ? '—' : String(overview.fixtures)}
          />
          <MonitoringMetricCard
            label="Settled"
            value={overview?.settled == null ? '—' : String(overview.settled)}
            hint={
              overview?.activations != null
                ? `Attivazioni: ${overview.activations}`
                : undefined
            }
          />
        </div>
        <p className="text-sm text-slate-600">
          Vista «{view}»: apri <strong>Lab</strong> per trend ECharts, modelli e attivazioni. Il
          Monitoraggio Segnali operativo resta separato in sidebar.
        </p>
      </div>
    )
  }

  if (view === 'lab') {
    return (
      <div className="-mx-2">
        <MonitoraggioSegnaliLab />
      </div>
    )
  }

  if (view === 'exports') {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-600">Export analysis pack Segnali.</p>
        <MonitoringExportMenu
          moduleKey="signals"
          dateFrom={dateFrom}
          dateTo={dateTo}
          competitionId={competitionId}
        />
      </div>
    )
  }

  return (
    <MonitoringEmptyState
      title="Vista non riconosciuta"
      reason={`La vista «${view}» non è configurata per Segnali.`}
    />
  )
}
