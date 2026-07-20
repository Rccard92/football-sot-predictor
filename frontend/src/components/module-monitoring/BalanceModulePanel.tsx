import { RicercaCredibilitaXPage } from '../../pages/RicercaCredibilitaXPage'
import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import {
  BalanceDataHealthView,
  BalanceDominanceAnalysisView,
  BalanceDrawCredibilityAnalysisView,
  BalanceEmpiricalOverview,
  BalanceF36AnalysisView,
  BalanceGapAnalysisView,
  BalanceStabilityView,
} from './balance/BalanceAnalysisViews'
import { BalanceEmpiricalDatasetView } from './balance/BalanceEmpiricalDatasetView'
import { MonitoringEmptyState } from './MonitoringEmptyState'
import { MonitoringExportMenu } from './MonitoringExportMenu'

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
  const common = {
    dateFrom,
    dateTo,
    competitionId,
    cohortFilter,
  }

  if (view === 'overview') {
    return (
      <div className="space-y-4">
        {overview ? (
          <p className="text-xs text-slate-500">
            Operativo: Ufficiale monitorato · Maturità:{' '}
            {overview.scientific_maturity || 'empirical_dataset_collecting'}
          </p>
        ) : null}
        <BalanceEmpiricalOverview {...common} />
      </div>
    )
  }

  if (view === 'empirical-dataset') {
    return <BalanceEmpiricalDatasetView {...common} />
  }

  if (view === 'geometry-f36') {
    return <BalanceF36AnalysisView {...common} />
  }

  if (view === 'dominance') {
    return <BalanceDominanceAnalysisView {...common} />
  }

  if (view === 'draw-credibility') {
    return (
      <div className="space-y-6">
        <BalanceDrawCredibilityAnalysisView {...common} />
        <div className="border-t border-slate-200 pt-4">
          <h4 className="mb-2 text-sm font-semibold text-slate-800">
            Laboratorio legacy — Ricerca Credibilità X
          </h4>
          <div className="-mx-2">
            <RicercaCredibilitaXPage />
          </div>
        </div>
      </div>
    )
  }

  if (view === 'gap-coherence') {
    return <BalanceGapAnalysisView {...common} />
  }

  if (view === 'stability') {
    return <BalanceStabilityView {...common} />
  }

  if (view === 'data-health') {
    return <BalanceDataHealthView {...common} />
  }

  if (view === 'exports') {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-600">
          Export analysis pack Balance v5 (forensic v7 + analisi empirica Step 2B).
        </p>
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
