import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import {
  GoalIntensityOverviewView,
  GoalIntensityDimensionsView,
  GoalIntensityCandidatesView,
  GoalIntensityProspectiveResultsView,
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

  if (view === 'overview') {
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

  return (
    <MonitoringEmptyState
      title="Vista non riconosciuta"
      reason={`La vista «${view}» non è configurata per Goal Intensity v5.`}
    />
  )
}
