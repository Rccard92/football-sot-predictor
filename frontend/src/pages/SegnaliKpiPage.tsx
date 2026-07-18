import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import type { KpiSignalActivationRow } from '../lib/cecchinoKpiSignalsApi'
import { KpiRatingBucketCarousel } from '../components/cecchino-kpi-signals/KpiRatingBucketCarousel'
import {
  KpiSignalDetailDrawer,
  type KpiDrawerState,
} from '../components/cecchino-kpi-signals/KpiSignalDetailDrawer'
import { KpiSignalsActivationsLab } from '../components/cecchino-kpi-signals/KpiSignalsActivationsLab'
import { KpiSignalsEmptyState } from '../components/cecchino-kpi-signals/KpiSignalsEmptyState'
import { KpiSignalsFilters } from '../components/cecchino-kpi-signals/KpiSignalsFilters'
import {
  KpiSignalsHeatmapLab,
  type KpiHeatmapSelection,
} from '../components/cecchino-kpi-signals/KpiSignalsHeatmapLab'
import { KpiSignalsInfoPanel } from '../components/cecchino-kpi-signals/KpiSignalsInfoPanel'
import { KpiSignalsMetricRibbon } from '../components/cecchino-kpi-signals/KpiSignalsMetricRibbon'
import { KpiSignalsPageHeader } from '../components/cecchino-kpi-signals/KpiSignalsPageHeader'
import { KpiSignalsSkeleton } from '../components/cecchino-kpi-signals/KpiSignalsSkeleton'
import { KpiSignalsTopRankingLab } from '../components/cecchino-kpi-signals/KpiSignalsTopRankingLab'
import { PurchasabilityAuditBody } from '../components/cecchino-purchasability-research/PurchasabilityAuditBody'
import { PurchasabilityStatisticalResearchBody } from '../components/cecchino-purchasability-research/PurchasabilityStatisticalResearchBody'
import { useCecchinoKpiSignals } from '../hooks/useCecchinoKpiSignals'
import { useCecchinoPurchasabilityAudit } from '../hooks/useCecchinoPurchasabilityAudit'
import { useCecchinoPurchasabilityStatisticalResearch } from '../hooks/useCecchinoPurchasabilityStatisticalResearch'

type TabId = 'signals' | 'purchasability'
type PurchasabilitySubTab = 'audit' | 'statistical-2a'

export function SegnaliKpiPage() {
  const [tab, setTab] = useState<TabId>('signals')
  const [purchSubTab, setPurchSubTab] = useState<PurchasabilitySubTab>('audit')
  const kpi = useCecchinoKpiSignals()
  const purch = useCecchinoPurchasabilityAudit()
  const purchStat = useCecchinoPurchasabilityStatisticalResearch()
  const [drawer, setDrawer] = useState<KpiDrawerState>(null)
  const [heatmapFilter, setHeatmapFilter] = useState<KpiHeatmapSelection | null>(null)

  useEffect(() => {
    void kpi.loadAll()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleBucketSelect = useCallback(
    (bucket: string) => {
      kpi.setRatingBucket(bucket)
      setHeatmapFilter(null)
      void kpi.loadAll()
    },
    [kpi],
  )

  const filteredActivations = useMemo(() => {
    if (!heatmapFilter) return kpi.activations
    return kpi.activations.filter(
      (a) =>
        a.selection_label === heatmapFilter.selectionLabel &&
        a.rating_bucket === heatmapFilter.ratingBucket,
    )
  }, [kpi.activations, heatmapFilter])

  const handleHeatmapCellClick = useCallback(
    (cell: KpiHeatmapSelection) => {
      setHeatmapFilter(cell)
      kpi.setRatingBucket(cell.ratingBucket)
      const related = kpi.activations.filter(
        (a) =>
          a.selection_label === cell.selectionLabel && a.rating_bucket === cell.ratingBucket,
      )
      setDrawer({ type: 'heatmap', cell, activations: related })
    },
    [kpi.activations, kpi.setRatingBucket],
  )

  const handleRowClick = useCallback((row: KpiSignalActivationRow) => {
    setDrawer({ type: 'activation', row })
  }, [])

  const emptyVariant = useMemo(() => {
    const diag = kpi.summary?.diagnostics
    if (!kpi.summary) return null
    if ((diag?.today_fixtures_count ?? 0) === 0) return 'no_fixtures' as const
    if ((diag?.kpi_signals_created ?? 0) === 0 && (diag?.fixtures_with_kpi_panel ?? 0) > 0) {
      return 'not_synced' as const
    }
    if ((kpi.summary.overall.activations ?? 0) === 0 && (diag?.kpi_rows_below_50 ?? 0) > 0) {
      return 'no_rating' as const
    }
    if ((kpi.summary.overall.activations ?? 0) === 0) return 'not_synced' as const
    return null
  }, [kpi.summary])

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="min-h-screen bg-gradient-to-b from-slate-50/90 via-white to-cyan-50/20"
    >
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6">
        <KpiSignalsPageHeader />

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setTab('signals')}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              tab === 'signals'
                ? 'bg-slate-900 text-white'
                : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
            }`}
          >
            Segnali
          </button>
          <button
            type="button"
            onClick={() => setTab('purchasability')}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              tab === 'purchasability'
                ? 'bg-slate-900 text-white'
                : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
            }`}
          >
            Acquistabilità
          </button>
        </div>

        {tab === 'purchasability' ? (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setPurchSubTab('audit')}
                className={`rounded-md px-3 py-1 text-sm ${
                  purchSubTab === 'audit'
                    ? 'bg-cyan-800 text-white'
                    : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
                }`}
              >
                Audit
              </button>
              <button
                type="button"
                onClick={() => setPurchSubTab('statistical-2a')}
                className={`rounded-md px-3 py-1 text-sm ${
                  purchSubTab === 'statistical-2a'
                    ? 'bg-cyan-800 text-white'
                    : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
                }`}
              >
                Ricerca statistica — Fase 2A
              </button>
            </div>

            {purchSubTab === 'audit' ? (
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
            ) : (
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
            )}
          </div>
        ) : (
          <>
            <KpiSignalsFilters
              dateFrom={kpi.dateFrom}
              dateTo={kpi.dateTo}
              ratingBucket={kpi.ratingBucket}
              selectionKey={kpi.selectionKey}
              evaluationStatus={kpi.evaluationStatus}
              countryName={kpi.countryName}
              leagueName={kpi.leagueName}
              loading={kpi.loading}
              actionLoading={kpi.actionLoading}
              onDateFromChange={kpi.setDateFrom}
              onDateToChange={kpi.setDateTo}
              onRatingBucketChange={kpi.setRatingBucket}
              onSelectionKeyChange={kpi.setSelectionKey}
              onEvaluationStatusChange={kpi.setEvaluationStatus}
              onCountryNameChange={kpi.setCountryName}
              onLeagueNameChange={kpi.setLeagueName}
              onRefresh={() => void kpi.loadAll()}
              onSync={() => void kpi.runSync()}
              onRevaluate={() => void kpi.runRevaluate()}
              onExport={kpi.exportCsv}
            />

            {kpi.loading && !kpi.summary ? <KpiSignalsSkeleton /> : null}

            {!kpi.loading && emptyVariant ? (
              <KpiSignalsEmptyState
                variant={emptyVariant}
                onSync={() => void kpi.runSync()}
                actionLoading={kpi.actionLoading}
              />
            ) : null}

            {kpi.summary && !emptyVariant ? (
              <>
                <KpiRatingBucketCarousel
                  buckets={kpi.summary.by_rating_bucket}
                  selectedBucket={kpi.ratingBucket}
                  onSelect={handleBucketSelect}
                  onClearFilter={() => {
                    setHeatmapFilter(null)
                    void kpi.loadAll()
                  }}
                />
                <KpiSignalsMetricRibbon overall={kpi.summary.overall} />
                <KpiSignalsHeatmapLab
                  cells={kpi.summary.heatmap.cells}
                  onCellClick={handleHeatmapCellClick}
                />
                <KpiSignalsTopRankingLab top={kpi.summary.top} />
                <KpiSignalsActivationsLab rows={filteredActivations} onRowClick={handleRowClick} />
                <KpiSignalsInfoPanel />
              </>
            ) : null}

            <KpiSignalDetailDrawer state={drawer} onClose={() => setDrawer(null)} />
          </>
        )}
      </div>
    </motion.div>
  )
}
