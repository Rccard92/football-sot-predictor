import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import type { SignalActivationRow } from '../lib/cecchinoSignalsApi'
import { SignalsActivationsLab } from '../components/cecchino-lab/SignalsActivationsLab'
import {
  SignalsDetailDrawer,
  type DrawerState,
} from '../components/cecchino-lab/SignalsDetailDrawer'
import {
  SignalsHeatmapLab,
  type HeatmapCellSelection,
} from '../components/cecchino-lab/SignalsHeatmapLab'
import { SignalsLabEmptyState } from '../components/cecchino-lab/SignalsLabEmptyState'
import { SignalsLabFilters } from '../components/cecchino-lab/SignalsLabFilters'
import { SignalsLabInfoPanel } from '../components/cecchino-lab/SignalsLabInfoPanel'
import { SignalsFormulaLegendAccordion } from '../components/cecchino/signals/SignalsFormulaLegendAccordion'
import { SignalMinBookOddsPanel } from '../components/cecchino/SignalMinBookOddsPanel'
import { SignalsLabPageHeader } from '../components/cecchino-lab/SignalsLabPageHeader'
import { SignalsLabSkeleton } from '../components/cecchino-lab/SignalsLabSkeleton'
import { SignalsMetricRibbon } from '../components/cecchino-lab/SignalsMetricRibbon'
import { SignalsTopRankingLab } from '../components/cecchino-lab/SignalsTopRankingLab'
import { SignalsTrendChart } from '../components/cecchino-lab/SignalsTrendChart'
import { WeightModelCarousel } from '../components/cecchino-lab/WeightModelCarousel'
import { useCecchinoSignalsLab } from '../hooks/useCecchinoSignalsLab'

function formatModelWeightsSubtitle(weights: string): string {
  const parts = weights.split(' / ')
  if (parts.length !== 4) return `Pesi: ${weights}`
  return `Pesi: Totali ${parts[0]}%, Casa/Trasferta ${parts[1]}%, Ultime 6 ${parts[2]}%, Ultime 5 C/F ${parts[3]}%`
}

export function MonitoraggioSegnaliLab() {
  const lab = useCecchinoSignalsLab()
  const [drawer, setDrawer] = useState<DrawerState>(null)
  const [heatmapFilter, setHeatmapFilter] = useState<{
    signalGroup: string
    sourceColumn: string
  } | null>(null)

  useEffect(() => {
    void lab.loadAll()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps -- initial load only

  const handleRefresh = useCallback(() => {
    lab.resetDefaultOnDateChange()
    void lab.loadAll()
  }, [lab])

  const filteredActivations = useMemo(() => {
    if (!heatmapFilter) return lab.activations
    if (heatmapFilter.sourceColumn === 'TOTALE') {
      return lab.activations.filter((a) => a.signal_group === heatmapFilter.signalGroup)
    }
    return lab.activations.filter(
      (a) =>
        a.signal_group === heatmapFilter.signalGroup &&
        a.source_column === heatmapFilter.sourceColumn,
    )
  }, [lab.activations, heatmapFilter])

  const handleHeatmapCellClick = useCallback(
    (cell: HeatmapCellSelection) => {
      setHeatmapFilter({
        signalGroup: cell.signalGroup,
        sourceColumn: cell.sourceColumn,
      })
      const related =
        cell.sourceColumn === 'TOTALE'
          ? lab.activations.filter((a) => a.signal_group === cell.signalGroup)
          : lab.activations.filter(
              (a) =>
                a.signal_group === cell.signalGroup && a.source_column === cell.sourceColumn,
            )
      setDrawer({ type: 'heatmap', cell, activations: related })
    },
    [lab.activations],
  )

  const handleRowClick = useCallback((row: SignalActivationRow) => {
    setDrawer({ type: 'activation', row })
  }, [])

  const weightsSubtitle = lab.selectedModel
    ? formatModelWeightsSubtitle(lab.selectedModel.weights)
    : ''

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="min-h-screen bg-gradient-to-b from-slate-50/90 via-white to-cyan-50/20"
    >
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6">
        <SignalsLabPageHeader />

        <SignalsLabFilters
          dateFrom={lab.dateFrom}
          dateTo={lab.dateTo}
          signalGroup={lab.signalGroup}
          sourceColumn={lab.sourceColumn}
          evaluationStatus={lab.evaluationStatus}
          countryName={lab.countryName}
          leagueName={lab.leagueName}
          loading={lab.loading}
          actionLoading={lab.actionLoading}
          onDateFromChange={lab.setDateFrom}
          onDateToChange={lab.setDateTo}
          onSignalGroupChange={lab.setSignalGroup}
          onSourceColumnChange={lab.setSourceColumn}
          onEvaluationStatusChange={lab.setEvaluationStatus}
          onCountryNameChange={lab.setCountryName}
          onLeagueNameChange={lab.setLeagueName}
          onRefresh={handleRefresh}
          onBacktest={() => void lab.runBacktest()}
          onRevaluate={() => void lab.runRevaluate()}
          onExport={lab.exportCsv}
        />

        <SignalMinBookOddsPanel
          variant="lab"
          dateFrom={lab.dateFrom}
          dateTo={lab.dateTo}
          onBacktestComplete={async () => {
            await lab.loadAll()
          }}
        />

        {lab.loading && !lab.summary ? (
          <SignalsLabSkeleton />
        ) : (
          <>
            {lab.hasFixturesInRange && !lab.hasAnyModelData && (
              <SignalsLabEmptyState
                variant="no_models"
                onBacktest={() => void lab.runBacktest()}
                actionLoading={lab.actionLoading}
              />
            )}

            {!lab.hasFixturesInRange && lab.summary?.diagnostics?.today_fixtures_count === 0 && (
              <SignalsLabEmptyState variant="no_fixtures" />
            )}

            {lab.modelsSummary && (
              <WeightModelCarousel
                models={lab.modelsSummary.models}
                selectedModelKey={lab.selectedModelKey}
                onSelect={(key) => void lab.selectModel(key)}
              />
            )}

            {lab.summary && (
              <>
                <SignalsMetricRibbon
                  overall={lab.summary.overall}
                  selectedModel={lab.selectedModel}
                  modelKey={lab.selectedModelKey}
                />

                {lab.modelsSummary?.models?.length && lab.summary?.overall && (
                  <SignalsTrendChart models={lab.modelsSummary.models} summary={lab.summary} />
                )}

                <SignalsHeatmapLab
                  summary={lab.summary}
                  modelLabel={lab.selectedModel?.short_label ?? `Modello ${lab.selectedModelKey}`}
                  weightsSubtitle={weightsSubtitle}
                  onCellClick={handleHeatmapCellClick}
                />

                <SignalsTopRankingLab summary={lab.summary} />

                <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-sm font-semibold text-slate-800">Dettaglio partite</h2>
                    {heatmapFilter && (
                      <button
                        type="button"
                        onClick={() => setHeatmapFilter(null)}
                        className="text-xs text-indigo-600 hover:underline"
                      >
                        Rimuovi filtro heatmap
                      </button>
                    )}
                  </div>
                  <div className="mt-3">
                    <SignalsActivationsLab
                      items={filteredActivations}
                      onRowClick={handleRowClick}
                    />
                  </div>
                </section>

                <SignalsFormulaLegendAccordion />

                <SignalsLabInfoPanel />
              </>
            )}
          </>
        )}

        <SignalsDetailDrawer state={drawer} onClose={() => setDrawer(null)} />
      </div>
    </motion.div>
  )
}
