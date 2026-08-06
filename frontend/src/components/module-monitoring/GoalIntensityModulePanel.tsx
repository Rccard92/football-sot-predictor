import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import {
  GoalIntensityOverviewView,
  GoalIntensityDimensionsView,
  GoalIntensityCandidatesView,
  GoalIntensityProspectiveResultsView,
  GoalIntensityBenchmarkView,
  GoalIntensityPhase2CView,
  GoalIntensityCalibrationView,
  GoalIntensityStabilityView,
  GoalIntensityReadinessView,
  GoalIntensityDataHealthView,
  GoalIntensityExportView,
} from './goal/GoalIntensityViews'
import { MonitoringEmptyState } from './MonitoringEmptyState'

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
  cohortFilter = 'all',
}: Props) {
  const common = {
    dateFrom,
    dateTo,
    competitionId,
    cohortFilter,
  }

  if (view === 'overview' || view === 'market-outputs') {
    return <GoalIntensityOverviewView {...common} />
  }

  if (view === 'dimensions') {
    return <GoalIntensityDimensionsView {...common} />
  }

  if (view === 'candidates') {
    return <GoalIntensityCandidatesView {...common} />
  }

  if (view === 'prospective-results') {
    return <GoalIntensityProspectiveResultsView {...common} />
  }

  if (view === 'benchmark-v4-v5' || view === 'benchmark') {
    return <GoalIntensityBenchmarkView {...common} />
  }

  if (view === 'variants-phase-2c') {
    return <GoalIntensityPhase2CView {...common} />
  }

  if (view === 'calibration') {
    return <GoalIntensityCalibrationView {...common} />
  }

  if (view === 'stability') {
    return <GoalIntensityStabilityView {...common} />
  }

  if (view === 'readiness') {
    return <GoalIntensityReadinessView {...common} />
  }

  if (view === 'data-health') {
    return <GoalIntensityDataHealthView {...common} />
  }

  if (view === 'export') {
    return <GoalIntensityExportView {...common} />
  }

  if (view === 'research-archive') {
    return (
      <div className="space-y-4">
        <MonitoringEmptyState
          title="Archivio ricerca"
          reason="Le viste research (candidati, Phase 2C, benchmark prospettico) non sono caricate di default. Seleziona una sotto-vista dall’archivio quando serve."
        />
        <GoalIntensityCandidatesView {...common} />
      </div>
    )
  }

  return (
    <MonitoringEmptyState
      title="Vista non riconosciuta"
      reason={`La vista «${view}» non è configurata per Goal Intensity v5.`}
    />
  )
}
