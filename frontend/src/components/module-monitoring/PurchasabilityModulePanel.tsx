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

export function PurchasabilityModulePanel({
  view,
  dateFrom,
  dateTo,
  competitionId,
  overview,
  cohortFilter = 'all',
}: Props) {
  if (view === 'overview') {
    const statusRaw = overview?.status || null
    return (
      <div className="space-y-4">
        {cohortFilter !== 'all' && cohortFilter !== 'prospective_persisted' ? (
          <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Filtro coorte «{cohortFilter}»: le metriche di readiness/promozione restano sulla
            coorte prospettica.
          </p>
        ) : null}
        {overview ? <ModuleCardSections item={overview} /> : null}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MonitoringMetricCard
            label="Fixture prospettive"
            value={
              overview?.prospective_fixtures == null
                ? '—'
                : String(overview.prospective_fixtures)
            }
          />
          <MonitoringMetricCard
            label="Fixture storiche"
            value={
              overview?.historical_fixtures == null
                ? '—'
                : String(overview.historical_fixtures)
            }
          />
          <MonitoringMetricCard
            label="Righe storiche"
            value={
              overview?.historical_rows == null
                ? '—'
                : String(overview.historical_rows)
            }
          />
          <MonitoringMetricCard
            label="Righe valutate (won/lost)"
            value={
              overview?.evaluated_rows == null
                ? overview?.historical_settled_rows == null
                  ? '—'
                  : String(overview.historical_settled_rows)
                : String(overview.evaluated_rows)
            }
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MonitoringMetricCard
            label="Pending"
            value={
              overview?.pending_rows == null ? '—' : String(overview.pending_rows)
            }
          />
          <MonitoringMetricCard
            label="Result missing"
            value={
              overview?.result_missing_rows == null
                ? '—'
                : String(overview.result_missing_rows)
            }
          />
          <MonitoringMetricCard
            label="Righe escluse data quality"
            value={
              overview?.data_quality_excluded_rows == null
                ? '—'
                : String(overview.data_quality_excluded_rows)
            }
          />
          <MonitoringMetricCard
            label="Stato readiness"
            value={monitoringStatusLabel(overview?.readiness_status ?? statusRaw)}
            ariaLabel={statusRaw ? `Stato ${statusRaw}` : undefined}
          />
        </div>
        <p className="text-xs text-slate-500">
          Righe totali validation: {overview?.validation_rows_total ?? '—'}. Readiness/promozione
          restano solo prospettiche.
        </p>
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
          sourceCohort={cohortFilter}
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
