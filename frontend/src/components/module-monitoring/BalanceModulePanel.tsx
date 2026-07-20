import { RicercaCredibilitaXPage } from '../../pages/RicercaCredibilitaXPage'
import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import { BalanceEmpiricalDatasetView } from './balance/BalanceEmpiricalDatasetView'
import { MonitoringEmptyState } from './MonitoringEmptyState'
import { MonitoringExportMenu } from './MonitoringExportMenu'
import { MonitoringMetricCard } from './MonitoringMetricCard'
import { ModuleCardSections } from './ModuleCardSections'
import { monitoringStatusLabel } from './moduleMonitoringUi'

type Props = {
  view: string
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  overview?: ModuleOverviewItem | null
  cohortFilter?: string
}

export function BalanceModulePanel({
  view,
  dateFrom,
  dateTo,
  competitionId,
  overview,
  cohortFilter = 'all',
}: Props) {
  if (view === 'overview' || view === 'geometry-f36' || view === 'dominance' || view === 'gap-coherence' || view === 'data-health') {
    const statusRaw = overview?.status || 'official_monitored'
    return (
      <div className="space-y-4">
        {cohortFilter !== 'all' && cohortFilter !== 'prospective_persisted' ? (
          <div className="rounded-xl border border-amber-200/80 bg-amber-50/70 px-3 py-2 text-sm text-amber-950">
            Filtro coorte «{cohortFilter}»: le metriche di readiness restano sulla coorte
            prospettica; lo storico non promuove.
          </div>
        ) : null}
        {overview ? <ModuleCardSections item={overview} /> : null}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MonitoringMetricCard
            label="Copertura descrittiva"
            value={overview?.coverage_descriptive_ratio || '—'}
          />
          <MonitoringMetricCard
            label="Timestamp verificati"
            value={overview?.timestamp_verified_ratio || '—'}
          />
          <MonitoringMetricCard
            label="Snapshot prospettici"
            value={
              overview?.prospective_persisted == null
                ? '—'
                : String(overview.prospective_persisted)
            }
          />
          <MonitoringMetricCard
            label="Fixture settled"
            value={overview?.settled == null ? '—' : String(overview.settled)}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <MonitoringMetricCard
            label="Stato"
            value={monitoringStatusLabel(statusRaw)}
            ariaLabel={`Stato ${statusRaw}`}
          />
          <MonitoringMetricCard
            label="Ricostruite"
            value={
              overview?.reconstructed_fixtures == null
                ? '—'
                : String(overview.reconstructed_fixtures)
            }
          />
          <MonitoringMetricCard
            label="Fixture analizzate"
            value={overview?.fixtures == null ? '—' : String(overview.fixtures)}
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

  if (view === 'empirical-dataset') {
    return (
      <BalanceEmpiricalDatasetView
        dateFrom={dateFrom}
        dateTo={dateTo}
        competitionId={competitionId}
        cohortFilter={cohortFilter}
      />
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
          sourceCohort={cohortFilter}
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
