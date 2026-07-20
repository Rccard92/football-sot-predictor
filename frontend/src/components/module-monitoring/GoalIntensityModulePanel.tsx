import { RicercaIntensitaGoalPage } from '../../pages/RicercaIntensitaGoalPage'
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
  cohortFilter?: string
}

export function GoalIntensityModulePanel({
  view,
  dateFrom,
  dateTo,
  competitionId,
  overview,
  cohortFilter = 'all',
}: Props) {
  if (
    view === 'overview' ||
    view === 'candidates' ||
    view === 'prospective-results' ||
    view === 'calibration' ||
    view === 'data-health'
  ) {
    const statusRaw = overview?.status || 'preview_research'
    return (
      <div className="space-y-4">
        {cohortFilter !== 'all' && cohortFilter !== 'prospective_persisted' ? (
          <div className="rounded-xl border border-amber-200/80 bg-amber-50/70 px-3 py-2 text-sm text-amber-950">
            Filtro coorte «{cohortFilter}»: i minimi prospettici e i bundle Goal non cambiano.
          </div>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MonitoringMetricCard
            label="Stato"
            value={monitoringStatusLabel(statusRaw)}
            ariaLabel={`Stato ${statusRaw}`}
          />
          <MonitoringMetricCard label="Versione" value={overview?.version || 'goal_intensity_v5_preview'} />
          <MonitoringMetricCard
            label="Fixture periodo"
            value={overview?.fixtures == null ? '—' : String(overview.fixtures)}
          />
          <MonitoringMetricCard
            label="Settled"
            value={overview?.settled == null ? '—' : String(overview.settled)}
          />
        </div>
        <p className="text-sm text-slate-600">
          Vista «{view}»: usa il laboratorio ricerca (tab Preview) per candidati, calibrazione e
          export backend già distinti (preview_summary … preview_bundle_definition). Coverage
          dettagliata non è forzata a 0% se il denominatore non è noto.
        </p>
      </div>
    )
  }

  if (view === 'research') {
    return (
      <div className="-mx-2">
        <RicercaIntensitaGoalPage />
      </div>
    )
  }

  if (view === 'exports') {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-600">Export analysis pack Goal Intensity v5.</p>
        <MonitoringExportMenu
          moduleKey="goal-intensity-v5"
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
      reason={`La vista «${view}» non è configurata per Goal Intensity.`}
    />
  )
}
