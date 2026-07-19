import { useEffect } from 'react'
import { PurchasabilityAuditBody } from '../cecchino-purchasability-research/PurchasabilityAuditBody'
import { PurchasabilityStatisticalResearchBody } from '../cecchino-purchasability-research/PurchasabilityStatisticalResearchBody'
import { PurchasabilityResidualReliabilityBody } from '../cecchino-purchasability-research/PurchasabilityResidualReliabilityBody'
import { PurchasabilityValidationBody } from '../cecchino-purchasability-research/PurchasabilityValidationBody'
import { useCecchinoPurchasabilityAudit } from '../../hooks/useCecchinoPurchasabilityAudit'
import { useCecchinoPurchasabilityStatisticalResearch } from '../../hooks/useCecchinoPurchasabilityStatisticalResearch'
import { useCecchinoPurchasabilityResidualReliability } from '../../hooks/useCecchinoPurchasabilityResidualReliability'
import { useCecchinoPurchasabilityValidation } from '../../hooks/useCecchinoPurchasabilityValidation'
import { MonitoringEmptyState } from './MonitoringEmptyState'
import { MonitoringExportMenu } from './MonitoringExportMenu'
import type { ModuleOverviewItem } from '../../lib/cecchinoModuleMonitoringApi'
import { MonitoringMetricCard } from './MonitoringMetricCard'
import { coverageDisplay, monitoringStatusLabel } from './moduleMonitoringUi'

type Props = {
  view: string
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  overview?: ModuleOverviewItem | null
}

export function PurchasabilityModulePanel({
  view,
  dateFrom,
  dateTo,
  competitionId,
  overview,
}: Props) {
  if (view === 'overview') {
    const cov = coverageDisplay(overview?.coverage ?? null, overview?.coverage != null)
    const statusRaw = overview?.status || null
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MonitoringMetricCard
            label="Stato"
            value={monitoringStatusLabel(statusRaw)}
            ariaLabel={statusRaw ? `Stato ${statusRaw}` : undefined}
          />
          <MonitoringMetricCard label="Coverage" value={cov.text} />
          <MonitoringMetricCard
            label="Fixture"
            value={overview?.fixtures == null ? '—' : String(overview.fixtures)}
          />
          <MonitoringMetricCard
            label="Settled"
            value={overview?.settled == null ? '—' : String(overview.settled)}
          />
        </div>
        <p className="text-sm text-slate-600">
          Apri la vista Validazione per metriche, gate e grafici. I laboratori Audit / 2A /
          Residuale restano disponibili senza avvio parallelo.
        </p>
      </div>
    )
  }

  if (view === 'validation') return <PurchasabilityValidationView />
  if (view === 'audit') return <PurchasabilityAuditView />
  if (view === 'statistical-research') return <PurchasabilityStatView />
  if (view === 'residual-reliability') return <PurchasabilityResidualView />
  if (view === 'exports') {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-600">
          Pacchetto analisi ChatGPT e riepiloghi JSON per il modulo Acquistabilità.
        </p>
        <MonitoringExportMenu
          moduleKey="purchasability"
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
      reason={`La vista «${view}» non è configurata per Acquistabilità.`}
    />
  )
}

function PurchasabilityValidationView() {
  const v = useCecchinoPurchasabilityValidation()
  useEffect(() => {
    void v.loadSync()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <PurchasabilityValidationBody
      health={v.health}
      summary={v.summary}
      readiness={v.readiness}
      loading={v.loading}
      error={v.error}
      job={v.job}
      dateFrom={v.dateFrom}
      dateTo={v.dateTo}
      marketKey={v.marketKey}
      bootstrapIterations={v.bootstrapIterations}
      onDateFrom={v.setDateFrom}
      onDateTo={v.setDateTo}
      onMarketKey={v.setMarketKey}
      onBootstrap={v.setBootstrapIterations}
      onRefresh={() => void v.loadSync()}
      onStartJob={() => void v.startJob()}
      filters={v.filters}
    />
  )
}

function PurchasabilityAuditView() {
  const purch = useCecchinoPurchasabilityAudit()
  useEffect(() => {
    void purch.loadAudit()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <PurchasabilityAuditBody
      audit={purch.audit}
      dataset={purch.dataset}
      loading={purch.loading}
      error={purch.error}
      dateFrom={purch.dateFrom}
      dateTo={purch.dateTo}
      marketFamily={purch.marketFamily}
      onDateFrom={purch.setDateFrom}
      onDateTo={purch.setDateTo}
      onMarketFamily={purch.setMarketFamily}
      onRefresh={() => void purch.loadAudit()}
      onDatasetPage={(offset) => void purch.loadDatasetPage(offset)}
      filters={purch.filters}
    />
  )
}

function PurchasabilityStatView() {
  const purchStat = useCecchinoPurchasabilityStatisticalResearch()
  useEffect(() => {
    void purchStat.load()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <PurchasabilityStatisticalResearchBody
      data={purchStat.data}
      loading={purchStat.loading}
      error={purchStat.error}
      detailWarning={purchStat.detailWarning}
      job={purchStat.job}
      dateFrom={purchStat.dateFrom}
      dateTo={purchStat.dateTo}
      selection={purchStat.selection}
      bootstrapIterations={purchStat.bootstrapIterations}
      onDateFrom={purchStat.setDateFrom}
      onDateTo={purchStat.setDateTo}
      onSelection={purchStat.setSelection}
      onBootstrap={purchStat.setBootstrapIterations}
      onRefresh={() => void purchStat.load()}
      filters={purchStat.filters}
    />
  )
}

function PurchasabilityResidualView() {
  const purchResidual = useCecchinoPurchasabilityResidualReliability()
  useEffect(() => {
    void purchResidual.load()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <PurchasabilityResidualReliabilityBody
      data={purchResidual.data}
      loading={purchResidual.loading}
      error={purchResidual.error}
      detailWarning={purchResidual.detailWarning}
      job={purchResidual.job}
      dateFrom={purchResidual.dateFrom}
      dateTo={purchResidual.dateTo}
      selection={purchResidual.selection}
      bootstrapIterations={purchResidual.bootstrapIterations}
      onDateFrom={purchResidual.setDateFrom}
      onDateTo={purchResidual.setDateTo}
      onSelection={purchResidual.setSelection}
      onBootstrap={purchResidual.setBootstrapIterations}
      onRefresh={() => void purchResidual.load()}
      filters={purchResidual.filters}
    />
  )
}
