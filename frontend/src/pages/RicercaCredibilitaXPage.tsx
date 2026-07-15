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
import { useCecchinoDrawCredibilityDataset } from '../hooks/useCecchinoDrawCredibilityDataset'
import { useCecchinoDrawCredibilityResearch } from '../hooks/useCecchinoDrawCredibilityResearch'
import { isoDaysAgoLocal, todayLocalIso } from '../utils/dateLocal'

type TabId = 'audit' | 'dataset'

export function RicercaCredibilitaXPage() {
  const [activeTab, setActiveTab] = useState<TabId>('audit')
  const [dateFrom, setDateFrom] = useState(() => isoDaysAgoLocal(90))
  const [dateTo, setDateTo] = useState(() => todayLocalIso())
  const [competitionId, setCompetitionId] = useState('')

  const sharedFilters = { dateFrom, dateTo, competitionId }
  const research = useCecchinoDrawCredibilityResearch(sharedFilters)
  const datasetHook = useCecchinoDrawCredibilityDataset(sharedFilters)

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
      ) : (
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
      )}
    </motion.div>
  )
}
