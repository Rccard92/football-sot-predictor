import { useCallback, useState } from 'react'
import { ContextBanner } from '../components/ContextBanner'
import { RoundAnalysisV31CalibrationSimulatorSection } from '../components/backtest/RoundAnalysisV31CalibrationSimulatorSection'
import { RoundAnalysisV31PatternAnalysisSection } from '../components/backtest/RoundAnalysisV31PatternAnalysisSection'
import {
  PredictiveAuditPanel,
  PredictiveDiagnosticsPanel,
  PredictiveNextDirectionPanel,
} from '../components/predictive/PredictiveDiagnosticsPanel'
import { PredictiveSimulatorVerdictPanel } from '../components/predictive/PredictiveSimulatorVerdictPanel'
import { PredictiveStructuralIssuesPanel } from '../components/predictive/PredictiveStructuralIssuesPanel'
import { useCompetition } from '../contexts/CompetitionContext'
import {
  DEFAULT_SEASON,
  getV31CalibrationSimulator,
  getV31PatternAnalysis,
  type V31CalibrationSimulator,
  type V31PatternAnalysis,
} from '../lib/api'
import { seasonLabelFromYear } from '../components/backtest/roundAnalysisUtils'

const PAGE_TABS = [
  { id: 'overview', label: 'Panoramica' },
  { id: 'simulator', label: 'Simulatore v3.1' },
  { id: 'pattern', label: 'Pattern Analysis' },
] as const

type PageTabId = (typeof PAGE_TABS)[number]['id']

export function PredictiveSimulatorPage() {
  const { selectedCompetition, selectedCompetitionId } = useCompetition()
  const seasonYear = selectedCompetition?.season ?? DEFAULT_SEASON
  const seasonLabel = seasonLabelFromYear(seasonYear)

  const [pageTab, setPageTab] = useState<PageTabId>('overview')
  const [simulator, setSimulator] = useState<V31CalibrationSimulator | null>(null)
  const [pattern, setPattern] = useState<V31PatternAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const runAll = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoading(true)
    setError(null)
    try {
      const [simRes, patRes] = await Promise.all([
        getV31CalibrationSimulator(selectedCompetitionId, seasonYear, {
          strategy: 'all',
          strategyStatus: 'active',
        }),
        getV31PatternAnalysis(selectedCompetitionId, seasonYear, { includeFixtures: true }),
      ])
      setSimulator(simRes)
      setPattern(patRes)
    } catch (e) {
      setSimulator(null)
      setPattern(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selectedCompetitionId, seasonYear])

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Simulatore Predittivo</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Laboratorio per confrontare strategie numeriche SOT, analizzare pattern di errore e costruire
          la futura v3.1.
        </p>
      </header>

      <ContextBanner showModelSelector={false} seasonLabel={seasonLabel} comparedModelsLabel="v3.1 lab" />

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={loading || selectedCompetitionId == null}
          className="rounded-lg border border-violet-700 bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50"
          onClick={() => void runAll()}
        >
          {loading ? 'Analisi in corso…' : 'Esegui analisi'}
        </button>
        {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {PAGE_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`rounded-t px-4 py-2 text-sm font-medium ${
              pageTab === t.id
                ? 'border border-b-0 border-slate-200 bg-white text-violet-900'
                : 'text-slate-600 hover:text-slate-900'
            }`}
            onClick={() => setPageTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {pageTab === 'overview' ? (
        <div className="space-y-4">
          <PredictiveSimulatorVerdictPanel simulator={simulator} pattern={pattern} />
          <PredictiveStructuralIssuesPanel pattern={pattern} />
          <PredictiveDiagnosticsPanel pattern={pattern} />
          <PredictiveNextDirectionPanel />
          <PredictiveAuditPanel pattern={pattern} />
        </div>
      ) : null}

      {pageTab === 'simulator' ? (
        <RoundAnalysisV31CalibrationSimulatorSection
          competitionId={selectedCompetitionId}
          seasonYear={seasonYear}
          embedded
          hidePageHeader
          externalData={simulator}
          externalLoading={loading}
          externalError={error}
          onExternalRun={runAll}
        />
      ) : null}

      {pageTab === 'pattern' ? (
        <RoundAnalysisV31PatternAnalysisSection
          competitionId={selectedCompetitionId}
          seasonYear={seasonYear}
          embedded
          hidePageHeader
          externalData={pattern}
          externalLoading={loading}
          externalError={error}
          onExternalRun={runAll}
        />
      ) : null}
    </div>
  )
}
