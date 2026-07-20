import { MonitoraggioSegnaliLab } from '../../pages/MonitoraggioSegnaliLab'
import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import { MonitoringEmptyState } from './MonitoringEmptyState'
import { MonitoringExportMenu } from './MonitoringExportMenu'
import { MonitoringMetricCard } from './MonitoringMetricCard'
import { ModuleCardSections } from './ModuleCardSections'

type Props = {
  view: string
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  overview?: ModuleOverviewItem | null
  cohortFilter?: string
}

export function SignalsModulePanel({
  view,
  dateFrom,
  dateTo,
  competitionId,
  overview,
  cohortFilter = 'all',
}: Props) {
  if (view === 'overview' || view === 'performance' || view === 'models' || view === 'trends') {
    return (
      <div className="space-y-4">
        {cohortFilter !== 'all' && cohortFilter !== 'prospective_persisted' ? (
          <div className="rounded-xl border border-amber-200/80 bg-amber-50/70 px-3 py-2 text-sm text-amber-950">
            Filtro coorte «{cohortFilter}»: le metriche ufficiali restano sulle attivazioni
            pre-match verificate.
          </div>
        ) : null}
        {overview ? <ModuleCardSections item={overview} /> : null}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <MonitoringMetricCard
            label="Fixture con segnali correnti"
            value={
              overview?.fixtures_with_current_signals == null
                ? overview?.fixtures == null
                  ? '—'
                  : String(overview.fixtures)
                : String(overview.fixtures_with_current_signals)
            }
          />
          <MonitoringMetricCard
            label="Attivazioni correnti"
            value={
              overview?.current_activations == null
                ? '—'
                : String(overview.current_activations)
            }
          />
          <MonitoringMetricCard
            label="Attivazioni correnti valutate"
            value={
              overview?.current_activations_evaluated == null
                ? '—'
                : String(overview.current_activations_evaluated)
            }
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <MonitoringMetricCard
            label="Attivazioni storiche totali"
            value={
              overview?.historical_activations_total == null
                ? overview?.historical_activations == null
                  ? '—'
                  : String(overview.historical_activations)
                : String(overview.historical_activations_total)
            }
          />
          <MonitoringMetricCard
            label="Pre-match verificate"
            value={
              overview?.verified_pre_match_count == null
                ? '—'
                : String(overview.verified_pre_match_count)
            }
          />
          <MonitoringMetricCard
            label="Post-kickoff escluse"
            value={
              overview?.post_kickoff_excluded_count == null
                ? overview?.unusable_count == null
                  ? '—'
                  : String(overview.unusable_count)
                : String(overview.post_kickoff_excluded_count)
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
          sourceCohort={cohortFilter}
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
