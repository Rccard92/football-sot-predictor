import { useState } from 'react'
import { ContextBanner } from '../components/ContextBanner'
import { RoundAnalysisAccordion, ModelSummaryBar } from '../components/backtest/RoundAnalysisAccordion'
import { RoundAnalysisFixtureTable } from '../components/backtest/RoundAnalysisFixtureTable'
import { RoundAnalysisForm } from '../components/backtest/RoundAnalysisForm'
import { dataQualityBadgeClass } from '../components/backtest/roundAnalysisUtils'
import { useCompetition } from '../contexts/CompetitionContext'
import { DEFAULT_SEASON, type RoundAnalysisDetail } from '../lib/api'

export function Backtest() {
  const { selectedCompetition, selectedCompetitionId } = useCompetition()
  const seasonYear = selectedCompetition?.season ?? DEFAULT_SEASON
  const [detail, setDetail] = useState<RoundAnalysisDetail | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Backtest</h1>
        <p className="mt-1 text-sm text-slate-600">
          Analizza una giornata del campionato e confronta i modelli SOT.
        </p>
      </header>

      <ContextBanner />

      <RoundAnalysisForm
        competitionId={selectedCompetitionId}
        seasonYear={seasonYear}
        onAnalyzed={setDetail}
        onReloadList={() => setReloadToken((t) => t + 1)}
      />

      <RoundAnalysisAccordion
        competitionId={selectedCompetitionId}
        seasonYear={seasonYear}
        selectedId={detail?.id ?? null}
        onSelect={setDetail}
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
            <span
              className={`rounded-full px-2 py-0.5 text-xs ${dataQualityBadgeClass(
                detail.data_quality_summary_json?.badge,
              )}`}
            >
              Qualità dati: {detail.data_quality_summary_json?.badge ?? '—'}
            </span>
          </div>
          <ModelSummaryBar summary={detail.model_summary_json} />
          <RoundAnalysisFixtureTable fixtures={detail.fixtures} />
        </section>
      ) : null}
    </div>
  )
}
