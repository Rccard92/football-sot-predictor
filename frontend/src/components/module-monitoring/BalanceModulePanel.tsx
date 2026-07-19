import { RicercaCredibilitaXPage } from '../../pages/RicercaCredibilitaXPage'
import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import { MonitoringEmptyState } from './MonitoringEmptyState'
import { MonitoringExportMenu } from './MonitoringExportMenu'
import { MonitoringMetricCard } from './MonitoringMetricCard'
import { coverageDisplay, monitoringStatusLabel } from './moduleMonitoringUi'

type Props = {
  view: string
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  overview?: ModuleOverviewItem | null
}

export function BalanceModulePanel({
  view,
  dateFrom,
  dateTo,
  competitionId,
  overview,
}: Props) {
  if (view === 'overview' || view === 'geometry-f36' || view === 'dominance' || view === 'gap-coherence' || view === 'data-health') {
    const cov = coverageDisplay(overview?.coverage ?? null, overview?.coverage != null)
    const statusRaw = overview?.status || 'official_monitored'
    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-violet-200/70 bg-violet-50/50 px-3 py-2 text-sm text-violet-900">
          Monitoraggio descrittivo — validazione empirica avanzata in preparazione
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MonitoringMetricCard
            label="Stato"
            value={monitoringStatusLabel(statusRaw)}
            ariaLabel={`Stato ${statusRaw}`}
          />
          <MonitoringMetricCard label="Coverage snapshot" value={cov.text} />
          <MonitoringMetricCard
            label="Fixture analizzate"
            value={overview?.fixtures == null ? '—' : String(overview.fixtures)}
          />
          <MonitoringMetricCard
            label="Fixture settled"
            value={overview?.settled == null ? '—' : String(overview.settled)}
          />
        </div>
        <p className="text-sm text-slate-600">
          Vista «{view}»: distribuzione pilastri e health da snapshot salvati. Per Credibilità X
          apri la vista dedicata (laboratorio esistente).
        </p>
        {(overview?.warnings || []).map((w) => (
          <p key={w} className="text-xs text-amber-700">
            {w}
          </p>
        ))}
      </div>
    )
  }

  if (view === 'draw-credibility') {
    return (
      <div className="-mx-2">
        <RicercaCredibilitaXPage />
      </div>
    )
  }

  if (view === 'exports') {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-600">Export analysis pack Balance v5.</p>
        <MonitoringExportMenu
          moduleKey="balance-v5"
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
      reason={`La vista «${view}» non è configurata per Balance v5.`}
    />
  )
}
