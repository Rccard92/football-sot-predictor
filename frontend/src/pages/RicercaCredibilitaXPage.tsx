import { useState } from 'react'
import { motion } from 'framer-motion'
import { CecchinoStatusMessage } from '../components/cecchino/CecchinoStatusMessage'
import { DrawCredibilityAntiLeakagePanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityAntiLeakagePanel'
import { DrawCredibilityCandidateFormulasLegend } from '../components/cecchino-draw-credibility-research/DrawCredibilityCandidateFormulasLegend'
import { DrawCredibilityCohortComparisonTable } from '../components/cecchino-draw-credibility-research/DrawCredibilityCohortComparisonTable'
import { DrawCredibilityConsistencyPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityConsistencyPanel'
import { DrawCredibilityCoverageFunnel } from '../components/cecchino-draw-credibility-research/DrawCredibilityCoverageFunnel'
import { DrawCredibilityDatasetFilters } from '../components/cecchino-draw-credibility-research/DrawCredibilityDatasetFilters'
import { DrawCredibilityDatasetKpiCards } from '../components/cecchino-draw-credibility-research/DrawCredibilityDatasetKpiCards'
import { DrawCredibilityDatasetPreviewTable } from '../components/cecchino-draw-credibility-research/DrawCredibilityDatasetPreviewTable'
import { DrawCredibilityDebugPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityDebugPanel'
import { DrawCredibilityExclusionTable } from '../components/cecchino-draw-credibility-research/DrawCredibilityExclusionTable'
import { DrawCredibilityGlobalExclusionsPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityGlobalExclusionsPanel'
import { DrawCredibilityGlobalPipelinePanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityGlobalPipelinePanel'
import { DrawCredibilityLeagueTable } from '../components/cecchino-draw-credibility-research/DrawCredibilityLeagueTable'
import { DrawCredibilityMonthlyTable } from '../components/cecchino-draw-credibility-research/DrawCredibilityMonthlyTable'
import { DrawCredibilityResearchEmptyState } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchEmptyState'
import { DrawCredibilityResearchFilters } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchFilters'
import { DrawCredibilityResearchKpiCards } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchKpiCards'
import { DrawCredibilityResearchNotes } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchNotes'
import { DrawCredibilityResearchPageHeader } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchPageHeader'
import { DrawCredibilityResearchSkeleton } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchSkeleton'
import { DrawCredibilityResearchTabs } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchTabs'
import { DrawCredibilityVersionTable } from '../components/cecchino-draw-credibility-research/DrawCredibilityVersionTable'
import { DrawCredibilityCandidatePatternsPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityCandidatePatternsPanel'
import { DrawCredibilityFeatureDetailPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityFeatureDetailPanel'
import { DrawCredibilityFeatureLeaderboardTable } from '../components/cecchino-draw-credibility-research/DrawCredibilityFeatureLeaderboardTable'
import { DrawCredibilityInteractionPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityInteractionPanel'
import { DrawCredibilityLeagueStabilityPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityLeagueStabilityPanel'
import { DrawCredibilityMarketAnalysisPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityMarketAnalysisPanel'
import { DrawCredibilityProbabilityCalibrationPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityProbabilityCalibrationPanel'
import { DrawCredibilityRedundancyPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityRedundancyPanel'
import { DrawCredibilityResearchConclusionsPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchConclusionsPanel'
import { DrawCredibilityResearchMaturityPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchMaturityPanel'
import { DrawCredibilityStatisticsBaselinePanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityStatisticsBaselinePanel'
import { DrawCredibilityStatisticsFilters } from '../components/cecchino-draw-credibility-research/DrawCredibilityStatisticsFilters'
import { DrawCredibilityTemporalStabilityPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityTemporalStabilityPanel'
import { useCecchinoDrawCredibilityDataset } from '../hooks/useCecchinoDrawCredibilityDataset'
import { useCecchinoDrawCredibilityResearch } from '../hooks/useCecchinoDrawCredibilityResearch'
import { useCecchinoDrawCredibilityStatistics } from '../hooks/useCecchinoDrawCredibilityStatistics'
import { isoDaysAgoLocal, todayLocalIso } from '../utils/dateLocal'

type TabId = 'audit' | 'dataset' | 'statistics'

export function RicercaCredibilitaXPage() {
  const [activeTab, setActiveTab] = useState<TabId>('audit')
  const [dateFrom, setDateFrom] = useState(() => isoDaysAgoLocal(90))
  const [dateTo, setDateTo] = useState(() => todayLocalIso())
  const [competitionId, setCompetitionId] = useState('')

  const sharedFilters = { dateFrom, dateTo, competitionId }
  const research = useCecchinoDrawCredibilityResearch(sharedFilters)
  const datasetHook = useCecchinoDrawCredibilityDataset(sharedFilters)
  const statisticsHook = useCecchinoDrawCredibilityStatistics(sharedFilters)

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6 bg-gradient-to-b from-slate-50/80 to-white pb-10"
    >
      <DrawCredibilityResearchPageHeader />

      <DrawCredibilityResearchTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {activeTab === 'audit' ? (
        <>
          <DrawCredibilityResearchFilters
            dateFrom={dateFrom}
            dateTo={dateTo}
            competitionId={competitionId}
            onlyEligible={research.onlyEligible}
            loading={research.loading}
            onDateFromChange={setDateFrom}
            onDateToChange={setDateTo}
            onCompetitionIdChange={setCompetitionId}
            onOnlyEligibleChange={research.setOnlyEligible}
            onRunAudit={() => void research.runAudit()}
          />

          {research.error ? (
            <CecchinoStatusMessage variant="error" title="Errore audit" message={research.error} />
          ) : null}

          {research.audit?.warnings.map((w) => (
            <CecchinoStatusMessage key={w} variant="warning" title="Avviso" message={w} />
          ))}

          {research.loading ? <DrawCredibilityResearchSkeleton /> : null}

          {!research.loading && !research.audit && !research.error ? (
            <DrawCredibilityResearchEmptyState onRunAudit={() => void research.runAudit()} />
          ) : null}

          {!research.loading && research.audit ? (
            <div className="space-y-6">
              <DrawCredibilityResearchKpiCards
                summary={research.audit.summary}
                drawRatePct={research.audit.target_distribution.draw_rate_pct}
              />
              <DrawCredibilityCoverageFunnel
                summary={research.audit.summary}
                coverage={research.audit.coverage}
              />
              <DrawCredibilityExclusionTable reasons={research.audit.exclusion_reasons} />
              <DrawCredibilityLeagueTable rows={research.audit.by_league} />
              <DrawCredibilityMonthlyTable rows={research.audit.by_month} />
              <DrawCredibilityDebugPanel samples={research.audit.debug_samples} />
              <DrawCredibilityResearchNotes />
            </div>
          ) : null}
        </>
      ) : activeTab === 'dataset' ? (
        <>
          <DrawCredibilityDatasetFilters
            dateFrom={dateFrom}
            dateTo={dateTo}
            competitionId={competitionId}
            cohort={datasetHook.cohort}
            pageSize={datasetHook.pageSize}
            loading={datasetHook.loading}
            exporting={datasetHook.exporting}
            onDateFromChange={setDateFrom}
            onDateToChange={setDateTo}
            onCompetitionIdChange={setCompetitionId}
            onCohortChange={datasetHook.setCohort}
            onPageSizeChange={datasetHook.setPageSize}
            onLoadDataset={() => void datasetHook.loadDataset(1)}
            onExportCsv={() => void datasetHook.exportCsv()}
          />

          {datasetHook.error ? (
            <CecchinoStatusMessage variant="error" title="Errore dataset" message={datasetHook.error} />
          ) : null}

          {datasetHook.dataset?.warnings.map((w) => (
            <CecchinoStatusMessage key={w} variant="warning" title="Avviso" message={w} />
          ))}

          {datasetHook.loading ? <DrawCredibilityResearchSkeleton /> : null}

          {!datasetHook.loading && !datasetHook.dataset && !datasetHook.error ? (
            <DrawCredibilityResearchEmptyState
              onRunAudit={() => void datasetHook.loadDataset(1)}
              message='Seleziona filtri e coorte, poi premi "Carica dataset" per costruire il dataset storico deduplicato.'
              buttonLabel="Carica dataset"
            />
          ) : null}

          {!datasetHook.loading && datasetHook.dataset ? (
            <div className="space-y-6">
              <DrawCredibilityGlobalPipelinePanel pipeline={datasetHook.dataset.global_pipeline} />
              <DrawCredibilityDatasetKpiCards
                summary={datasetHook.dataset.selected_cohort_summary}
                drawRatePct={datasetHook.dataset.target_distribution.draw_rate_pct}
              />
              <DrawCredibilityCohortComparisonTable
                primary={datasetHook.dataset.primary_summary}
                sensitivity={datasetHook.dataset.sensitivity_summary}
                market={datasetHook.dataset.market_summary}
              />
              <DrawCredibilityAntiLeakagePanel
                selected={datasetHook.dataset.anti_leakage_selected}
                globalStats={datasetHook.dataset.anti_leakage_global}
              />
              <DrawCredibilityGlobalExclusionsPanel exclusions={datasetHook.dataset.global_exclusions} />
              <DrawCredibilityConsistencyPanel
                rows={datasetHook.dataset.cohort_consistency}
                checks={datasetHook.dataset.consistency_checks}
              />
              <DrawCredibilityVersionTable
                selected={datasetHook.dataset.version_distribution_selected}
                globalDistribution={datasetHook.dataset.version_distribution_global}
              />
              <DrawCredibilityDatasetPreviewTable
                rows={datasetHook.dataset.rows}
                page={datasetHook.dataset.pagination.page}
                totalPages={datasetHook.dataset.pagination.total_pages}
                totalRows={datasetHook.dataset.pagination.total_rows}
                onPageChange={(p) => void datasetHook.loadDataset(p)}
              />
              <DrawCredibilityCandidateFormulasLegend />
            </div>
          ) : null}
        </>
      ) : (
        <>
          <CecchinoStatusMessage
            variant="info"
            title="Analisi esplorativa"
            message="Questa analisi non modifica il modello produttivo Cecchino. I risultati sono diagnostici e soggetti a multiple comparisons."
          />

          <DrawCredibilityStatisticsFilters
            dateFrom={dateFrom}
            dateTo={dateTo}
            competitionId={competitionId}
            binCount={statisticsHook.binCount}
            minGroupSize={statisticsHook.minGroupSize}
            bootstrapIterations={statisticsHook.bootstrapIterations}
            loading={statisticsHook.loading}
            onDateFromChange={setDateFrom}
            onDateToChange={setDateTo}
            onCompetitionIdChange={setCompetitionId}
            onBinCountChange={statisticsHook.setBinCount}
            onMinGroupSizeChange={statisticsHook.setMinGroupSize}
            onBootstrapIterationsChange={statisticsHook.setBootstrapIterations}
            onRunAnalysis={() => void statisticsHook.runAnalysis()}
          />

          {statisticsHook.error ? (
            <CecchinoStatusMessage
              variant="error"
              title="Errore analisi"
              message={statisticsHook.error}
            />
          ) : null}

          {statisticsHook.loading ? <DrawCredibilityResearchSkeleton /> : null}

          {!statisticsHook.loading && !statisticsHook.lastAnalysis && !statisticsHook.error ? (
            <DrawCredibilityResearchEmptyState
              onRunAudit={() => void statisticsHook.runAnalysis()}
              message='Seleziona il periodo e premi "Esegui analisi" per calcolare statistiche univariate, calibrazione e ridondanze.'
              buttonLabel="Esegui analisi"
            />
          ) : null}

          {!statisticsHook.loading && statisticsHook.lastAnalysis ? (
            <div className="space-y-6">
              <DrawCredibilityResearchMaturityPanel
                maturity={statisticsHook.lastAnalysis.research_maturity}
                performance={statisticsHook.lastAnalysis.performance}
              />
              <DrawCredibilityStatisticsBaselinePanel
                primary={statisticsHook.lastAnalysis.dataset_summary.primary}
                sensitivity={statisticsHook.lastAnalysis.dataset_summary.sensitivity}
                market={statisticsHook.lastAnalysis.dataset_summary.market}
              />
              <DrawCredibilityFeatureLeaderboardTable
                rows={statisticsHook.lastAnalysis.feature_leaderboard}
              />
              <DrawCredibilityFeatureDetailPanel
                features={
                  statisticsHook.lastAnalysis.numeric_feature_analysis.eligible_primary ?? []
                }
                sensitivityFeatures={
                  statisticsHook.lastAnalysis.numeric_feature_analysis
                    .all_usable_sensitivity ?? []
                }
                primaryVsSensitivity={
                  statisticsHook.lastAnalysis.primary_vs_sensitivity.feature_comparisons
                }
              />
              <DrawCredibilityProbabilityCalibrationPanel
                calibration={statisticsHook.lastAnalysis.probability_calibration.primary_cecchino_x}
              />
              <DrawCredibilityRedundancyPanel
                redundancy={statisticsHook.lastAnalysis.redundancy_analysis}
              />
              <DrawCredibilityInteractionPanel
                interactions={statisticsHook.lastAnalysis.interaction_analysis}
              />
              <DrawCredibilityCandidatePatternsPanel
                patterns={statisticsHook.lastAnalysis.candidate_patterns}
              />
              <DrawCredibilityTemporalStabilityPanel
                temporal={statisticsHook.lastAnalysis.temporal_stability}
              />
              <DrawCredibilityLeagueStabilityPanel
                league={statisticsHook.lastAnalysis.league_stability}
                marketSummary={statisticsHook.lastAnalysis.dataset_summary.primary}
              />
              <DrawCredibilityMarketAnalysisPanel
                market={statisticsHook.lastAnalysis.market_analysis}
              />
              <DrawCredibilityResearchConclusionsPanel
                conclusions={statisticsHook.lastAnalysis.research_conclusions}
                nextPhaseRecommendations={
                  statisticsHook.lastAnalysis.next_phase_feature_recommendations ??
                  statisticsHook.lastAnalysis.research_conclusions
                    .next_phase_feature_recommendations
                }
              />
            </div>
          ) : null}
        </>
      )}
    </motion.div>
  )
}
