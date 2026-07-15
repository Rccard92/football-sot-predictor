import { motion } from 'framer-motion'
import { CecchinoStatusMessage } from '../components/cecchino/CecchinoStatusMessage'
import { DrawCredibilityCoverageFunnel } from '../components/cecchino-draw-credibility-research/DrawCredibilityCoverageFunnel'
import { DrawCredibilityDebugPanel } from '../components/cecchino-draw-credibility-research/DrawCredibilityDebugPanel'
import { DrawCredibilityExclusionTable } from '../components/cecchino-draw-credibility-research/DrawCredibilityExclusionTable'
import { DrawCredibilityLeagueTable } from '../components/cecchino-draw-credibility-research/DrawCredibilityLeagueTable'
import { DrawCredibilityMonthlyTable } from '../components/cecchino-draw-credibility-research/DrawCredibilityMonthlyTable'
import { DrawCredibilityResearchEmptyState } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchEmptyState'
import { DrawCredibilityResearchFilters } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchFilters'
import { DrawCredibilityResearchKpiCards } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchKpiCards'
import { DrawCredibilityResearchNotes } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchNotes'
import { DrawCredibilityResearchPageHeader } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchPageHeader'
import { DrawCredibilityResearchSkeleton } from '../components/cecchino-draw-credibility-research/DrawCredibilityResearchSkeleton'
import { useCecchinoDrawCredibilityResearch } from '../hooks/useCecchinoDrawCredibilityResearch'

export function RicercaCredibilitaXPage() {
  const research = useCecchinoDrawCredibilityResearch()

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6 bg-gradient-to-b from-slate-50/80 to-white pb-10"
    >
      <DrawCredibilityResearchPageHeader />

      <DrawCredibilityResearchFilters
        dateFrom={research.dateFrom}
        dateTo={research.dateTo}
        competitionId={research.competitionId}
        onlyEligible={research.onlyEligible}
        loading={research.loading}
        onDateFromChange={research.setDateFrom}
        onDateToChange={research.setDateTo}
        onCompetitionIdChange={research.setCompetitionId}
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
    </motion.div>
  )
}
