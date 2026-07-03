import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import type { KpiSignalActivationRow } from '../lib/cecchinoKpiSignalsApi'
import { KpiRatingBucketCarousel } from '../components/cecchino-kpi-signals/KpiRatingBucketCarousel'
import { KpiSignalDetailDrawer } from '../components/cecchino-kpi-signals/KpiSignalDetailDrawer'
import { KpiSignalsEmptyState, KpiSignalsInfoPanel, KpiSignalsSkeleton } from '../components/cecchino-kpi-signals/KpiSignalsInfoPanel'
import { KpiSignalsFilters } from '../components/cecchino-kpi-signals/KpiSignalsFilters'
import { KpiSignalsHeatmap, type KpiHeatmapSelection } from '../components/cecchino-kpi-signals/KpiSignalsHeatmap'
import { KpiSignalsMetricRibbon } from '../components/cecchino-kpi-signals/KpiSignalsMetricRibbon'
import { KpiSignalsPageHeader } from '../components/cecchino-kpi-signals/KpiSignalsPageHeader'
import { KpiSignalsTable } from '../components/cecchino-kpi-signals/KpiSignalsTable'
import { useCecchinoKpiSignals } from '../hooks/useCecchinoKpiSignals'

export function SegnaliKpiPage() {
  const kpi = useCecchinoKpiSignals()
  const [drawerRow, setDrawerRow] = useState<KpiSignalActivationRow | null>(null)
  const [heatmapFilter, setHeatmapFilter] = useState<KpiHeatmapSelection | null>(null)

  useEffect(() => {
    void kpi.loadAll()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleBucketSelect = useCallback(
    (bucket: string) => {
      kpi.setRatingBucket(bucket)
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
      className="min-h-screen bg-gradient-to-b from-slate-50/90 via-white to-cyan-50/20"
    >
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6">
        <KpiSignalsPageHeader />
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
          <KpiSignalsEmptyState variant={emptyVariant} onSync={() => void kpi.runSync()} />
        ) : null}

        {kpi.summary && !emptyVariant ? (
          <>
            <KpiRatingBucketCarousel
              buckets={kpi.summary.by_rating_bucket}
              selectedBucket={kpi.ratingBucket}
              onSelect={handleBucketSelect}
            />
            <KpiSignalsMetricRibbon overall={kpi.summary.overall} />
            <KpiSignalsHeatmap
              cells={kpi.summary.heatmap.cells}
              onCellClick={(cell) => {
                setHeatmapFilter(cell)
                kpi.setRatingBucket(cell.ratingBucket)
                kpi.setSelectionKey('')
              }}
            />
            <KpiSignalsTable rows={filteredActivations} onRowClick={setDrawerRow} />
            <KpiSignalsInfoPanel />
          </>
        ) : null}

        <KpiSignalDetailDrawer
          row={drawerRow}
          open={drawerRow != null}
          onClose={() => setDrawerRow(null)}
        />
      </div>
    </motion.div>
  )
}
