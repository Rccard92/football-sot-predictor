import { useCallback, useEffect, useState } from 'react'
import { ContextBanner } from '../components/ContextBanner'
import { RoundAnalysisV31CalibrationSimulatorSection } from '../components/backtest/RoundAnalysisV31CalibrationSimulatorSection'
import { RoundAnalysisV31PatternAnalysisSection } from '../components/backtest/RoundAnalysisV31PatternAnalysisSection'
import {
  PredictiveAiInsightsPanel,
  PredictiveLabAuditPanel,
} from '../components/predictive/PredictiveAiInsightsPanel'
import { PredictiveFixtureDiagnosisPanel } from '../components/predictive/PredictiveFixtureDiagnosisPanel'
import {
  PredictiveAuditPanel,
  PredictiveDiagnosticsPanel,
  PredictiveNextDirectionPanel,
} from '../components/predictive/PredictiveDiagnosticsPanel'
import {
  PredictiveCurrentRunCard,
  PredictiveRunHistoryPanel,
} from '../components/predictive/PredictiveRunHistoryPanel'
import { PredictiveSimulatorVerdictPanel } from '../components/predictive/PredictiveSimulatorVerdictPanel'
import { PredictiveStructuralIssuesPanel } from '../components/predictive/PredictiveStructuralIssuesPanel'
import { useCompetition } from '../contexts/CompetitionContext'
import {
  DEFAULT_SEASON,
  getPredictiveSimulatorRun,
  listPredictiveSimulatorRuns,
  postPredictiveSimulatorRun,
  type PredictiveRunListItem,
  type PredictiveSimulationRun,
  type V31CalibrationSimulator,
  type V31PatternAnalysis,
} from '../lib/api'
import { seasonLabelFromYear } from '../components/backtest/roundAnalysisUtils'

const PAGE_TABS = [
  { id: 'overview', label: 'Panoramica' },
  { id: 'history', label: 'Storico analisi' },
  { id: 'simulator', label: 'Simulatore v3.1' },
  { id: 'diagnosis', label: 'Diagnosi partite' },
  { id: 'pattern', label: 'Pattern Analysis' },
  { id: 'ai', label: 'Analisi AI' },
  { id: 'audit', label: 'Audit' },
] as const

type PageTabId = (typeof PAGE_TABS)[number]['id']

export function PredictiveSimulatorPage() {
  const { selectedCompetition, selectedCompetitionId } = useCompetition()
  const seasonYear = selectedCompetition?.season ?? DEFAULT_SEASON
  const seasonLabel = seasonLabelFromYear(seasonYear)

  const [pageTab, setPageTab] = useState<PageTabId>('overview')
  const [simulator, setSimulator] = useState<V31CalibrationSimulator | null>(null)
  const [pattern, setPattern] = useState<V31PatternAnalysis | null>(null)
  const [currentRunId, setCurrentRunId] = useState<number | null>(null)
  const [currentRun, setCurrentRun] = useState<PredictiveSimulationRun | null>(null)
  const [runHistory, setRunHistory] = useState<PredictiveRunListItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [savedMessage, setSavedMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshHistory = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setHistoryLoading(true)
    try {
      const runs = await listPredictiveSimulatorRuns(selectedCompetitionId, seasonYear)
      setRunHistory(runs)
    } catch {
      setRunHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }, [selectedCompetitionId, seasonYear])

  useEffect(() => {
    void refreshHistory()
  }, [refreshHistory])

  const loadFromRun = useCallback(async (runId: number) => {
    setLoading(true)
    setError(null)
    try {
      const run = await getPredictiveSimulatorRun(runId)
      setCurrentRunId(runId)
      setCurrentRun(run)
      setSimulator(run.simulator)
      setPattern(run.pattern)
      setSavedMessage(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const runAll = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoading(true)
    setError(null)
    setSavedMessage(null)
    try {
      const result = await postPredictiveSimulatorRun({
        competition_id: selectedCompetitionId,
        season_year: seasonYear,
        strategy: 'all',
        strategy_status: 'active',
        persist: true,
      })
      if (result.simulator) setSimulator(result.simulator)
      if (result.pattern) setPattern(result.pattern)
      if (result.run_id != null) {
        setCurrentRunId(result.run_id)
        const run = await getPredictiveSimulatorRun(result.run_id)
        setCurrentRun(run)
      }
      setSavedMessage(result.message ?? 'Analisi salvata nello storico')
      void refreshHistory()
    } catch (e) {
      setSimulator(null)
      setPattern(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selectedCompetitionId, seasonYear, refreshHistory])

  const labAudit = currentRun?.audit ?? {
    ...(simulator?.audit ?? {}),
    ...(pattern?.audit ?? {}),
    actual_post_match_only: true,
    win_quality_diagnostic_only: true,
    pattern_no_weight_mutation: true,
    openai_no_prediction_no_weight_mutation: true,
    betting_phase_enabled: false,
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Simulatore Predittivo</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Laboratorio persistente per confrontare strategie numeriche SOT, analizzare pattern di errore e
          costruire la futura v3.1.
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

      <PredictiveCurrentRunCard run={currentRun} savedMessage={savedMessage} />

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
        </div>
      ) : null}

      {pageTab === 'history' ? (
        <PredictiveRunHistoryPanel
          runs={runHistory}
          loading={historyLoading}
          currentRunId={currentRunId}
          onOpenRun={(id) => void loadFromRun(id)}
          onRefresh={() => void refreshHistory()}
        />
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

      {pageTab === 'diagnosis' ? <PredictiveFixtureDiagnosisPanel runId={currentRunId} /> : null}

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

      {pageTab === 'ai' ? <PredictiveAiInsightsPanel runId={currentRunId} /> : null}

      {pageTab === 'audit' ? (
        <div className="space-y-4">
          <PredictiveLabAuditPanel audit={labAudit} />
          <PredictiveAuditPanel pattern={pattern} />
        </div>
      ) : null}
    </div>
  )
}
