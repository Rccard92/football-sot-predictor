import { useState } from 'react'
import { ContextBanner } from '../components/ContextBanner'
import { RoundAnalysisAccordion, ModelSummaryBar } from '../components/backtest/RoundAnalysisAccordion'
import { RoundAnalysisDetailBox } from '../components/backtest/RoundAnalysisDetailBox'
import { RoundAnalysisFixtureTable } from '../components/backtest/RoundAnalysisFixtureTable'
import { RoundAnalysisForm } from '../components/backtest/RoundAnalysisForm'
import { dataQualityBadgeClass, seasonLabelFromYear, statusLabelIt } from '../components/backtest/roundAnalysisUtils'
import { useCompetition } from '../contexts/CompetitionContext'
import { DEFAULT_SEASON, type RoundAnalysisDetail } from '../lib/api'

export function Backtest() {
  const { selectedCompetition, selectedCompetitionId } = useCompetition()
  const seasonYear = selectedCompetition?.season ?? DEFAULT_SEASON
  const seasonLabel = seasonLabelFromYear(seasonYear)
  const [detail, setDetail] = useState<RoundAnalysisDetail | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [recommendedRound, setRecommendedRound] = useState<number | null>(null)

  const handleAnalyzed = (d: RoundAnalysisDetail) => {
    setDetail(d)
    if (d.first_recommended_round != null) {
      setRecommendedRound(d.first_recommended_round)
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Backtest</h1>
        <p className="mt-1 text-sm text-slate-600">
          Analizza una giornata del campionato e confronta i modelli SOT.
        </p>
      </header>

      <ContextBanner
        showModelSelector={false}
        seasonLabel={seasonLabel}
        comparedModelsLabel="v1.1 · v2.0 · v2.1"
      />

      <RoundAnalysisForm
        competitionId={selectedCompetitionId}
        seasonYear={seasonYear}
        seasonLabel={seasonLabel}
        firstRecommendedRound={recommendedRound ?? detail?.first_recommended_round ?? null}
        onAnalyzed={handleAnalyzed}
        onReloadList={() => setReloadToken((t) => t + 1)}
      />

      <RoundAnalysisAccordion
        competitionId={selectedCompetitionId}
        seasonYear={seasonYear}
        selectedId={detail?.id ?? null}
        onSelect={handleAnalyzed}
        onDeleted={(analysisId) => {
          if (detail?.id === analysisId) setDetail(null)
        }}
        reloadToken={reloadToken}
      />

      {detail ? (
        <section className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-semibold text-slate-900">
              Giornata {detail.round_number}
              <span className="ml-2 text-sm font-normal text-slate-500">
                versione {detail.analysis_version}
              </span>
            </h2>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
              {detail.status_label ?? statusLabelIt(detail.status)}
            </span>
            <span
              className={`rounded-full px-2 py-0.5 text-xs ${dataQualityBadgeClass(
                detail.data_quality_summary_json?.badge,
              )}`}
            >
              Qualità dati: {detail.data_quality_summary_json?.badge ?? '—'}
            </span>
          </div>

          <RoundAnalysisDetailBox detail={detail} />
          <ModelSummaryBar summary={detail.model_summary_json} />
          <RoundAnalysisFixtureTable fixtures={detail.fixtures} />
        </section>
      ) : null}
    </div>
  )
}
