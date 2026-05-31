import { useCallback, useEffect, useState } from 'react'
import {
  createBacktestRun,
  fetchBacktestApiRaw,
  getBacktestDebugHealth,
  getBacktestErrorCode,
  getBacktestErrorMessage,
  getBacktestHistoricalLineupAuditFixture,
  getBacktestHistoricalLineupAuditRound,
  getBacktestPointInTimeContext,
  getBacktestRun,
  getBacktestSotV21Preview,
  listBacktestDebugFixtures,
  listBacktestRuns,
  postBacktestSotV21MiniRun,
  postBacktestSotPickEvaluation,
  type BacktestFixtureCandidate,
  type BacktestRunRow,
  type HistoricalLineupAuditFixtureResponse,
  type HistoricalLineupAuditRoundResponse,
  type PointInTimeContextResponse,
  type SotPickEvaluationResponse,
  type SotV21MiniRunResponse,
  type SotV21PreviewResponse,
} from '../../lib/api'
import { useCompetition } from '../../contexts/CompetitionContext'
import { useModelSelection } from '../../contexts/ModelSelectionContext'
import { V21_MODEL } from '../../lib/modelVersions'

type OutcomeKind = 'ok' | 'test_ok' | 'error'

type Outcome = {
  kind: OutcomeKind
  httpStatus: number | null
  message: string
}

const DEBUG_CREATE_BODY = {
  market_key: 'shots_on_target',
  algorithm_version: V21_MODEL,
  mode: 'pre_lineup',
  fixture_scope: 'full_season',
  config_json: { default_ou_lines: [5.5, 6.5, 7.5, 8.5, 9.5] },
} as const

function formatNetworkError(e: unknown, label: string): string {
  const raw = e instanceof Error ? e.message : String(e)
  if (raw === 'Failed to fetch' || /network|abort/i.test(raw)) {
    return `${label}: errore di rete o backend non raggiungibile.`
  }
  return `${label}: ${raw}`
}

function outcomeClass(kind: OutcomeKind): string {
  if (kind === 'ok') return 'border-emerald-200 bg-emerald-50 text-emerald-900'
  if (kind === 'test_ok') return 'border-amber-200 bg-amber-50 text-amber-900'
  return 'border-rose-200 bg-rose-50 text-rose-900'
}

function outcomeLabel(kind: OutcomeKind): string {
  if (kind === 'ok') return 'OK'
  if (kind === 'test_ok') return 'Test OK'
  return 'Errore'
}

function parseManualFixtureId(raw: string): number | null {
  const n = parseInt(raw.trim(), 10)
  return Number.isFinite(n) && n > 0 ? n : null
}

function fmtMetric(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

function parseMiniRunRoundNumber(raw: string): number | null {
  const n = parseInt(raw.trim(), 10)
  return Number.isFinite(n) && n >= 1 ? n : null
}

function isPitLeakageCritical(row: {
  leakage_guard: boolean
  latest_fixture_used_at?: string | null
  cutoff_time: string
  warnings?: string[]
}): boolean {
  const latestBad =
    row.latest_fixture_used_at != null &&
    new Date(row.latest_fixture_used_at).getTime() >= new Date(row.cutoff_time).getTime()
  return !row.leakage_guard || latestBad || (row.warnings?.includes('possible_leakage') ?? false)
}

type PitSideTrace = SotV21PreviewResponse['home_trace']

function findSplitMacro(side: PitSideTrace | undefined) {
  return side?.macros?.find((m) => m.key === 'home_away_split')
}

function findPlayerLayerMacro(side: PitSideTrace | undefined) {
  return side?.macros?.find((m) => m.key === 'player_layer')
}

function countNeutralMacros(side: PitSideTrace | undefined): number {
  return (
    side?.macros?.filter(
      (m) => m.status === 'not_built_yet' || m.status === 'neutral_fallback',
    ).length ?? 0
  )
}

function pickOutcomeClass(outcome: string | null | undefined, noPick: boolean): string {
  if (noPick || !outcome) return 'text-slate-500'
  if (outcome === 'win') return 'font-semibold text-emerald-700'
  if (outcome === 'loss') return 'font-semibold text-rose-700'
  return 'text-slate-600'
}

function parseLinesInput(raw: string): number[] {
  return raw
    .split(',')
    .map((s) => parseFloat(s.trim()))
    .filter((n) => Number.isFinite(n) && n > 0)
}

export function BacktestDebugPanel() {
  const { selectedCompetition, selectedCompetitionId } = useCompetition()
  const { selectedModelVersion } = useModelSelection()

  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [lastJson, setLastJson] = useState<unknown>(null)
  const [runs, setRuns] = useState<BacktestRunRow[]>([])
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [lastCreatedRunId, setLastCreatedRunId] = useState<number | null>(null)
  const [detailZeroHint, setDetailZeroHint] = useState<string | null>(null)

  const [pitFixtures, setPitFixtures] = useState<BacktestFixtureCandidate[]>([])
  const [selectedFixtureId, setSelectedFixtureId] = useState<number | null>(null)
  const [manualFixtureId, setManualFixtureId] = useState('')
  const [pitOffset, setPitOffset] = useState(0)
  const [pitLimit, setPitLimit] = useState(20)
  const [pitTotal, setPitTotal] = useState(0)
  const [roundFilter, setRoundFilter] = useState('')
  const [roundFilterApplied, setRoundFilterApplied] = useState('')
  const [pitMode, setPitMode] = useState<'pre_lineup' | 'post_lineup' | 'historical_official_xi'>('pre_lineup')
  const [pitOutcome, setPitOutcome] = useState<Outcome | null>(null)
  const [pitJson, setPitJson] = useState<PointInTimeContextResponse | null>(null)
  const [pitPreviewJson, setPitPreviewJson] = useState<SotV21PreviewResponse | null>(null)
  const [pitLeakageCritical, setPitLeakageCritical] = useState(false)

  const [miniRunLimit, setMiniRunLimit] = useState(20)
  const [miniRunOffset, setMiniRunOffset] = useState(0)
  const [miniRunRoundNumber, setMiniRunRoundNumber] = useState('')
  const [miniRunMode, setMiniRunMode] = useState<'pre_lineup' | 'historical_official_xi'>('pre_lineup')
  const [miniRunIncludeTrace, setMiniRunIncludeTrace] = useState(false)
  const [miniRunOutcome, setMiniRunOutcome] = useState<Outcome | null>(null)
  const [miniRunJson, setMiniRunJson] = useState<SotV21MiniRunResponse | null>(null)

  const [pickEvalMode, setPickEvalMode] = useState<'pre_lineup' | 'historical_official_xi'>(
    'historical_official_xi',
  )
  const [pickEvalLimit, setPickEvalLimit] = useState(20)
  const [pickEvalOffset, setPickEvalOffset] = useState(0)
  const [pickEvalRoundNumber, setPickEvalRoundNumber] = useState('')
  const [pickEvalMinEdge, setPickEvalMinEdge] = useState('0.75')
  const [pickEvalLines, setPickEvalLines] = useState('5.5,6.5,7.5,8.5,9.5')
  const [pickEvalIncludeNoPick, setPickEvalIncludeNoPick] = useState(true)
  const [pickEvalOutcome, setPickEvalOutcome] = useState<Outcome | null>(null)
  const [pickEvalJson, setPickEvalJson] = useState<SotPickEvaluationResponse | null>(null)

  const [g2aRoundNumber, setG2aRoundNumber] = useState('')
  const [g2aOutcome, setG2aOutcome] = useState<Outcome | null>(null)
  const [g2aFixtureJson, setG2aFixtureJson] = useState<HistoricalLineupAuditFixtureResponse | null>(null)
  const [g2aRoundJson, setG2aRoundJson] = useState<HistoricalLineupAuditRoundResponse | null>(null)

  const needsCompetition = selectedCompetitionId == null

  const resolvePreviewFixtureId = useCallback((): number | null => {
    const manual = parseManualFixtureId(manualFixtureId)
    if (manual != null) return manual
    return selectedFixtureId
  }, [manualFixtureId, selectedFixtureId])

  const previewFixtureRow = useCallback((): BacktestFixtureCandidate | null => {
    const id = resolvePreviewFixtureId()
    if (id == null) return null
    return pitFixtures.find((f) => f.fixture_id === id) ?? null
  }, [pitFixtures, resolvePreviewFixtureId])

  const setResult = (kind: OutcomeKind, httpStatus: number | null, message: string, json: unknown) => {
    setOutcome({ kind, httpStatus, message })
    setLastJson(json)
  }

  const runHealth = useCallback(async () => {
    setLoadingId('health')
    setDetailZeroHint(null)
    try {
      const data = await getBacktestDebugHealth()
      const kind: OutcomeKind =
        data.status === 'ok' || data.status === 'degraded' ? 'ok' : 'error'
      const msg =
        data.status === 'degraded'
          ? 'Health degraded: tabelle backtest mancanti (SQLite locale senza migration). Registry OK.'
          : `Health OK — ${data.runs_count} run, mercati attivi: ${data.active_markets.join(', ') || '—'}`
      setResult(kind, 200, msg, data)
    } catch (e) {
      setResult('error', null, formatNetworkError(e, 'Health Backtest'), null)
    } finally {
      setLoadingId(null)
    }
  }, [])

  useEffect(() => {
    void runHealth()
  }, [runHealth])

  useEffect(() => {
    setPitOffset(0)
    setPitTotal(0)
    setPitFixtures([])
    setSelectedFixtureId(null)
    setManualFixtureId('')
    setRoundFilter('')
    setRoundFilterApplied('')
    setPitJson(null)
    setPitPreviewJson(null)
    setPitOutcome(null)
    setPitLeakageCritical(false)
  }, [selectedCompetitionId])

  const runCreate = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('create')
    setDetailZeroHint(null)
    try {
      const row = await createBacktestRun({
        competition_id: selectedCompetitionId,
        season_year: selectedCompetition?.season ?? undefined,
        ...DEBUG_CREATE_BODY,
        algorithm_version: selectedModelVersion || V21_MODEL,
      })
      setLastCreatedRunId(row.id)
      setSelectedRunId(row.id)
      setResult(
        'ok',
        200,
        `Run #${row.id} creata (status pending). Nessun backtest eseguito.`,
        row,
      )
    } catch (e) {
      setResult('error', null, formatNetworkError(e, 'Crea run debug'), null)
    } finally {
      setLoadingId(null)
    }
  }, [selectedCompetition?.season, selectedCompetitionId, selectedModelVersion])

  const runList = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('list')
    setDetailZeroHint(null)
    try {
      const data = await listBacktestRuns({
        competition_id: selectedCompetitionId,
        limit: 10,
      })
      setRuns(data.items)
      if (data.items.length > 0 && selectedRunId == null) {
        setSelectedRunId(data.items[0].id)
      }
      setResult(
        'ok',
        200,
        `${data.items.length} run (totale ${data.total}) per competition_id=${selectedCompetitionId}`,
        data,
      )
    } catch (e) {
      setResult('error', null, formatNetworkError(e, 'Lista run'), null)
    } finally {
      setLoadingId(null)
    }
  }, [selectedCompetitionId, selectedRunId])

  const runDetail = useCallback(async () => {
    setLoadingId('detail')
    const targetId =
      selectedRunId ?? lastCreatedRunId ?? (runs.length > 0 ? runs[0].id : null)
    if (targetId == null) {
      setResult(
        'error',
        null,
        'Nessuna run disponibile: crea una run o carica la lista.',
        null,
      )
      setLoadingId(null)
      return
    }
    try {
      const data = await getBacktestRun(targetId)
      setSelectedRunId(targetId)
      const zeros =
        data.predictions_count === 0 &&
        data.picks_count === 0 &&
        data.metrics_count === 0
      setDetailZeroHint(
        zeros
          ? 'Conteggi predictions/picks/metrics = 0 (atteso: nessun engine runtime in Step C.1).'
          : null,
      )
      setResult('ok', 200, `Dettaglio run #${data.id} (${data.status})`, data)
    } catch (e) {
      setDetailZeroHint(null)
      setResult('error', null, formatNetworkError(e, 'Dettaglio run'), null)
    } finally {
      setLoadingId(null)
    }
  }, [lastCreatedRunId, runs, selectedRunId])

  const runTestMarketPlanned = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('test-market')
    setDetailZeroHint(null)
    try {
      const { status, body } = await fetchBacktestApiRaw('POST', '/api/backtest/runs', {
        competition_id: selectedCompetitionId,
        season_year: selectedCompetition?.season ?? undefined,
        market_key: 'corners',
        algorithm_version: 'corners_v1_0',
        mode: 'pre_lineup',
        fixture_scope: 'full_season',
      })
      const code = getBacktestErrorCode(body)
      if (status === 422 && code === 'market_not_active') {
        setResult(
          'test_ok',
          status,
          `422 market_not_active — ${getBacktestErrorMessage(body) ?? 'mercato planned, non active'}`,
          body,
        )
      } else {
        setResult(
          'error',
          status,
          `Atteso 422 market_not_active, ricevuto ${status}${code ? ` (${code})` : ''}`,
          body,
        )
      }
    } catch (e) {
      setResult('error', null, formatNetworkError(e, 'Test market planned'), null)
    } finally {
      setLoadingId(null)
    }
  }, [selectedCompetition?.season, selectedCompetitionId])

  const runTestAlgorithmWrong = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('test-algo')
    setDetailZeroHint(null)
    try {
      const { status, body } = await fetchBacktestApiRaw('POST', '/api/backtest/runs', {
        competition_id: selectedCompetitionId,
        season_year: selectedCompetition?.season ?? undefined,
        market_key: 'shots_on_target',
        algorithm_version: 'corners_v1_0',
        mode: 'pre_lineup',
        fixture_scope: 'full_season',
      })
      const code = getBacktestErrorCode(body)
      if (status === 422 && code === 'invalid_algorithm_for_market') {
        setResult(
          'test_ok',
          status,
          `422 invalid_algorithm_for_market — ${getBacktestErrorMessage(body) ?? 'algoritmo non valido per SOT'}`,
          body,
        )
      } else {
        setResult(
          'error',
          status,
          `Atteso 422 invalid_algorithm_for_market, ricevuto ${status}${code ? ` (${code})` : ''}`,
          body,
        )
      }
    } catch (e) {
      setResult('error', null, formatNetworkError(e, 'Test algorithm errato'), null)
    } finally {
      setLoadingId(null)
    }
  }, [selectedCompetition?.season, selectedCompetitionId])

  const runListFixtures = useCallback(
    async (overrideOffset?: number, overrideLimit?: number, overrideRoundContains?: string) => {
      if (selectedCompetitionId == null) return
      const limit = overrideLimit ?? pitLimit
      const offset = overrideOffset ?? pitOffset
      const roundContains =
        overrideRoundContains !== undefined ? overrideRoundContains : roundFilterApplied
      setLoadingId('pit-fixtures')
      setPitJson(null)
      setPitLeakageCritical(false)
      try {
        const data = await listBacktestDebugFixtures({
          competition_id: selectedCompetitionId,
          season_year: selectedCompetition?.season,
          limit,
          offset,
          round_contains: roundContains.trim() || undefined,
        })
        setPitFixtures(data.items)
        setPitTotal(data.total)
        setPitOffset(data.offset)
        setPitLimit(data.limit)
        if (data.items.length > 0 && selectedFixtureId == null && parseManualFixtureId(manualFixtureId) == null) {
          setSelectedFixtureId(data.items[0].fixture_id)
        }
        const from = data.total === 0 ? 0 : data.offset + 1
        const to = data.offset + data.items.length
        const filterNote = roundContains.trim() ? ` — filtro round "${roundContains.trim()}"` : ''
        setPitOutcome({
          kind: 'ok',
          httpStatus: 200,
          message: `Mostrate ${from}–${to} di ${data.total}${filterNote}`,
        })
      } catch (e) {
        setPitOutcome({ kind: 'error', httpStatus: null, message: formatNetworkError(e, 'Lista fixture') })
      } finally {
        setLoadingId(null)
      }
    },
    [
      manualFixtureId,
      pitLimit,
      pitOffset,
      roundFilterApplied,
      selectedCompetition?.season,
      selectedCompetitionId,
      selectedFixtureId,
    ],
  )

  const runPreviewContext = useCallback(async () => {
    const fixtureId = resolvePreviewFixtureId()
    if (selectedCompetitionId == null || fixtureId == null) return
    setLoadingId('pit-preview')
    setPitLeakageCritical(false)
    try {
      const data = await getBacktestPointInTimeContext({
        competition_id: selectedCompetitionId,
        fixture_id: fixtureId,
        mode: pitMode,
      })
      setPitJson(data)
      const leakageBad = isPitLeakageCritical(data)
      setPitLeakageCritical(leakageBad)
      const kind: OutcomeKind = leakageBad ? 'error' : 'ok'
      setPitOutcome({
        kind,
        httpStatus: 200,
        message: leakageBad
          ? 'Context caricato ma leakage critico (possible_leakage o latest >= cutoff).'
          : `Context OK — leakage_guard=${data.leakage_guard}, prior lega=${data.league_prior_matches_count}`,
      })
    } catch (e) {
      setPitJson(null)
      setPitOutcome({ kind: 'error', httpStatus: null, message: formatNetworkError(e, 'Preview context') })
    } finally {
      setLoadingId(null)
    }
  }, [pitMode, resolvePreviewFixtureId, selectedCompetitionId])

  const runPreviewPrediction = useCallback(async () => {
    const fixtureId = resolvePreviewFixtureId()
    if (selectedCompetitionId == null || fixtureId == null) return
    if (pitMode === 'post_lineup') return
    setLoadingId('pit-prediction')
    try {
      const data = await getBacktestSotV21Preview({
        competition_id: selectedCompetitionId,
        fixture_id: fixtureId,
        mode: pitMode,
      })
      setPitPreviewJson(data)
      const leakageBad = isPitLeakageCritical(data)
      setPitLeakageCritical(leakageBad)
      const kind: OutcomeKind = leakageBad ? 'error' : 'ok'
      setPitOutcome({
        kind,
        httpStatus: 200,
        message: leakageBad
          ? 'Preview prediction con leakage critico (possible_leakage o latest >= cutoff).'
          : `Preview v2.1 PIT — totale ${data.prediction.total_predicted_sot ?? '—'}, errore abs ${data.errors.total_abs_error ?? '—'}`,
      })
    } catch (e) {
      setPitPreviewJson(null)
      setPitOutcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Preview prediction v2.1 PIT'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [pitMode, resolvePreviewFixtureId, selectedCompetitionId])

  const runMiniRunPreview = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('mini-run')
    try {
      const data = await postBacktestSotV21MiniRun({
        competition_id: selectedCompetitionId,
        mode: miniRunMode,
        limit: miniRunLimit,
        offset: miniRunOffset,
        round_number: parseMiniRunRoundNumber(miniRunRoundNumber),
        include_trace: miniRunIncludeTrace,
      })
      setMiniRunJson(data)
      const kind: OutcomeKind =
        data.status === 'ok' || data.status === 'partial_ok' ? 'ok' : 'error'
      setMiniRunOutcome({
        kind,
        httpStatus: 200,
        message: `Mini-run ${data.status} — ${data.summary.fixtures_processed} processate, ${data.summary.fixtures_failed} fallite, MAE ${fmtMetric(data.summary.total_mae)}`,
      })
    } catch (e) {
      setMiniRunJson(null)
      setMiniRunOutcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Mini-run preview v2.1 PIT'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [miniRunIncludeTrace, miniRunLimit, miniRunMode, miniRunOffset, miniRunRoundNumber, selectedCompetitionId])

  const runPickEvaluation = useCallback(async () => {
    if (selectedCompetitionId == null) return
    const lines = parseLinesInput(pickEvalLines)
    if (lines.length === 0) {
      setPickEvalOutcome({
        kind: 'error',
        httpStatus: null,
        message: 'Inserisci almeno una linea valida (es. 5.5,6.5,7.5).',
      })
      return
    }
    const minEdge = parseFloat(pickEvalMinEdge)
    if (!Number.isFinite(minEdge) || minEdge < 0) {
      setPickEvalOutcome({
        kind: 'error',
        httpStatus: null,
        message: 'Min edge non valido.',
      })
      return
    }
    setLoadingId('pick-eval')
    try {
      const data = await postBacktestSotPickEvaluation({
        competition_id: selectedCompetitionId,
        mode: pickEvalMode,
        limit: pickEvalLimit,
        offset: pickEvalOffset,
        round_number: parseMiniRunRoundNumber(pickEvalRoundNumber),
        lines,
        min_edge: minEdge,
        include_no_pick: pickEvalIncludeNoPick,
      })
      setPickEvalJson(data)
      const kind: OutcomeKind =
        data.status === 'ok' || data.status === 'partial_ok' ? 'ok' : 'error'
      setPickEvalOutcome({
        kind,
        httpStatus: 200,
        message: `Pick evaluation — ${data.summary.pick_opportunities} pick, hit rate ${fmtMetric(data.summary.hit_rate, 1)}%, db_writes=${String(data.db_writes)}`,
      })
    } catch (e) {
      setPickEvalJson(null)
      setPickEvalOutcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Pick evaluation preview'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [
    pickEvalIncludeNoPick,
    pickEvalLimit,
    pickEvalLines,
    pickEvalMinEdge,
    pickEvalMode,
    pickEvalOffset,
    pickEvalRoundNumber,
    selectedCompetitionId,
  ])

  const runG2aFixtureAudit = useCallback(async () => {
    if (selectedCompetitionId == null) return
    const fixtureId = resolvePreviewFixtureId()
    if (fixtureId == null) {
      setG2aOutcome({ kind: 'error', httpStatus: null, message: 'Seleziona o inserisci un fixture_id.' })
      return
    }
    setLoadingId('g2a-fixture')
    try {
      const data = await getBacktestHistoricalLineupAuditFixture({
        competition_id: selectedCompetitionId,
        fixture_id: fixtureId,
      })
      setG2aFixtureJson(data)
      setG2aRoundJson(null)
      setG2aOutcome({
        kind: 'ok',
        httpStatus: 200,
        message: `Audit fixture ${fixtureId} — home XI ${data.home.coverage.starters_count}, away XI ${data.away.coverage.starters_count}, db_writes=${String(data.db_writes)}`,
      })
    } catch (e) {
      setG2aFixtureJson(null)
      setG2aOutcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Audit fixture G2A'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [resolvePreviewFixtureId, selectedCompetitionId])

  const runG2aRoundAudit = useCallback(async () => {
    if (selectedCompetitionId == null) return
    const roundNum = parseMiniRunRoundNumber(g2aRoundNumber)
    if (roundNum == null) {
      setG2aOutcome({ kind: 'error', httpStatus: null, message: 'Inserisci una giornata esatta valida.' })
      return
    }
    setLoadingId('g2a-round')
    try {
      const data = await getBacktestHistoricalLineupAuditRound({
        competition_id: selectedCompetitionId,
        round_number: roundNum,
        limit: 20,
        offset: 0,
      })
      setG2aRoundJson(data)
      setG2aFixtureJson(null)
      setG2aOutcome({
        kind: 'ok',
        httpStatus: 200,
        message: `Audit giornata ${roundNum} — ${data.summary.fixtures_processed} fixture, XI entrambe ${data.summary.fixtures_with_official_xi_both_teams}, db_writes=${String(data.db_writes)}`,
      })
    } catch (e) {
      setG2aRoundJson(null)
      setG2aOutcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Audit giornata G2A'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [g2aRoundNumber, selectedCompetitionId])

  const applyRoundFilter = useCallback(() => {
    const applied = roundFilter.trim()
    setRoundFilterApplied(applied)
    setPitOffset(0)
    void runListFixtures(0, undefined, applied)
  }, [roundFilter, runListFixtures])

  const pitShownFrom = pitTotal === 0 ? 0 : pitOffset + 1
  const pitShownTo = pitOffset + pitFixtures.length
  const pitHasPrev = pitOffset > 0
  const pitHasNext = pitOffset + pitLimit < pitTotal
  const activePreviewId = resolvePreviewFixtureId()
  const activePreviewRow = previewFixtureRow()

  const buttons: {
    id: string
    label: string
    onClick: () => void
    needsComp?: boolean
  }[] = [
    { id: 'health', label: 'Health Backtest', onClick: () => void runHealth() },
    { id: 'create', label: 'Crea run debug v2.1', onClick: () => void runCreate(), needsComp: true },
    { id: 'list', label: 'Lista ultime run', onClick: () => void runList(), needsComp: true },
    { id: 'detail', label: 'Leggi ultima run', onClick: () => void runDetail() },
    {
      id: 'test-market',
      label: 'Test market planned',
      onClick: () => void runTestMarketPlanned(),
      needsComp: true,
    },
    {
      id: 'test-algo',
      label: 'Test algorithm errato',
      onClick: () => void runTestAlgorithmWrong(),
      needsComp: true,
    },
  ]

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-600">
        Pannello diagnostico Backtest Engine (Step C.1): CRUD run pending, health registry e test
        validazione. Nessun backtest runtime — le run restano in stato pending.
      </p>

      <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-sm text-slate-700">
        <div>
          <span className="font-medium">Campionato:</span>{' '}
          {selectedCompetition?.name ?? '—'}{' '}
          {selectedCompetitionId != null ? `(id=${selectedCompetitionId})` : ''}
        </div>
        <div>
          <span className="font-medium">Stagione:</span>{' '}
          {selectedCompetition?.season ?? '—'}
        </div>
        <div>
          <span className="font-medium">Modello UI:</span> {selectedModelVersion || V21_MODEL}
        </div>
      </div>

      {needsCompetition ? (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Seleziona un campionato nel selettore globale per abilitare creazione run, lista e test
          validazione.
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {buttons.map((b) => {
          const disabled = loadingId !== null || (b.needsComp && needsCompetition)
          return (
            <button
              key={b.id}
              type="button"
              disabled={disabled}
              onClick={b.onClick}
              className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-left text-sm font-medium text-indigo-900 transition hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loadingId === b.id ? '…' : b.label}
            </button>
          )
        })}
      </div>

      {outcome ? (
        <div className={`rounded-lg border px-3 py-2 text-sm ${outcomeClass(outcome.kind)}`}>
          <div className="font-semibold">
            {outcomeLabel(outcome.kind)}
            {outcome.httpStatus != null ? ` — HTTP ${outcome.httpStatus}` : ''}
          </div>
          <div className="mt-1">{outcome.message}</div>
        </div>
      ) : null}

      {detailZeroHint ? (
        <p className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900">
          {detailZeroHint}
        </p>
      ) : null}

      {lastJson != null ? (
        <pre className="max-h-64 overflow-auto rounded-lg border border-slate-200 bg-slate-900 p-3 text-xs text-slate-100">
          {JSON.stringify(lastJson, null, 2)}
        </pre>
      ) : null}

      {runs.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-600">
                <th className="px-2 py-1">ID</th>
                <th className="px-2 py-1">Market</th>
                <th className="px-2 py-1">Algorithm</th>
                <th className="px-2 py-1">Status</th>
                <th className="px-2 py-1">Created</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr
                  key={r.id}
                  className={`cursor-pointer border-b border-slate-100 hover:bg-indigo-50 ${
                    selectedRunId === r.id ? 'bg-indigo-100/60' : ''
                  }`}
                  onClick={() => setSelectedRunId(r.id)}
                >
                  <td className="px-2 py-1 font-mono">{r.id}</td>
                  <td className="px-2 py-1">{r.market_key}</td>
                  <td className="px-2 py-1 font-mono text-xs">{r.algorithm_version}</td>
                  <td className="px-2 py-1">{r.status}</td>
                  <td className="px-2 py-1 text-xs text-slate-600">
                    {r.created_at ? new Date(r.created_at).toLocaleString('it-IT') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="mt-6 border-t border-slate-200 pt-6">
        <h3 className="text-sm font-semibold text-slate-800">Point-in-time context (Step D)</h3>
        <p className="mt-1 text-sm text-slate-600">
          Preview read-only del contesto SOT as-of prima del kickoff. Nessuna prediction generata.
        </p>

        <div className="mt-3 flex flex-wrap items-end gap-2">
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runListFixtures(pitOffset)}
            className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm font-medium text-teal-900 hover:bg-teal-100 disabled:opacity-50"
          >
            {loadingId === 'pit-fixtures' ? '…' : 'Lista fixture storiche'}
          </button>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Limit
            <select
              value={pitLimit}
              disabled={loadingId !== null}
              onChange={(e) => {
                const next = Number(e.target.value)
                setPitLimit(next)
                setPitOffset(0)
                if (pitFixtures.length > 0 || pitTotal > 0) {
                  void runListFixtures(0, next)
                }
              }}
              className="rounded border border-slate-200 px-2 py-1 text-sm text-slate-800"
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Round contiene
            <input
              type="text"
              value={roundFilter}
              onChange={(e) => setRoundFilter(e.target.value)}
              placeholder="Regular Season - 20"
              className="min-w-[12rem] rounded border border-slate-200 px-2 py-1 text-sm text-slate-800"
            />
          </label>
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => applyRoundFilter()}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Applica filtro
          </button>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Fixture ID manuale
            <input
              type="text"
              value={manualFixtureId}
              onChange={(e) => setManualFixtureId(e.target.value)}
              placeholder="12345"
              className="w-28 rounded border border-slate-200 px-2 py-1 font-mono text-sm text-slate-800"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Mode
            <select
              value={pitMode}
              onChange={(e) =>
                setPitMode(e.target.value as 'pre_lineup' | 'post_lineup' | 'historical_official_xi')
              }
              className="rounded border border-slate-200 px-2 py-1"
            >
              <option value="pre_lineup">pre_lineup</option>
              <option value="post_lineup">post_lineup</option>
              <option value="historical_official_xi">historical_official_xi</option>
            </select>
          </label>
          {pitMode === 'historical_official_xi' ? (
            <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900">
              Historical Official XI — usa XI ufficiale storica, non pre-lineup puro
            </span>
          ) : null}
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition || activePreviewId == null}
            onClick={() => void runPreviewContext()}
            className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm font-medium text-teal-900 hover:bg-teal-100 disabled:opacity-50"
          >
            {loadingId === 'pit-preview' ? '…' : 'Preview context'}
          </button>
          <button
            type="button"
            disabled={
              loadingId !== null ||
              needsCompetition ||
              activePreviewId == null ||
              pitMode === 'post_lineup'
            }
            onClick={() => void runPreviewPrediction()}
            className="rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-sm font-medium text-violet-900 hover:bg-violet-100 disabled:opacity-50"
          >
            {loadingId === 'pit-prediction' ? '…' : 'Preview prediction v2.1 PIT'}
          </button>
        </div>

        <p className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          Preview tecnica point-in-time. Non è ancora una run backtest salvata. Serve per verificare
          che il calcolo su singola fixture usi solo dati precedenti al kickoff.
        </p>

        {activePreviewId != null ? (
          <div className="mt-3 rounded-lg border border-teal-100 bg-teal-50/50 px-3 py-2 text-sm text-slate-800">
            <div className="font-medium text-teal-900">Fixture per preview</div>
            <div className="mt-1 grid gap-1 sm:grid-cols-2">
              <div>
                <span className="font-medium">fixture_id:</span> {activePreviewId}
                {parseManualFixtureId(manualFixtureId) != null ? ' (manuale)' : ''}
              </div>
              {activePreviewRow ? (
                <>
                  <div>
                    <span className="font-medium">Match:</span> {activePreviewRow.home_team.name} vs{' '}
                    {activePreviewRow.away_team.name}
                  </div>
                  <div>
                    <span className="font-medium">Kickoff:</span>{' '}
                    {new Date(activePreviewRow.kickoff_at).toLocaleString('it-IT')}
                  </div>
                  <div>
                    <span className="font-medium">Round:</span> {activePreviewRow.round ?? '—'}
                  </div>
                  <div>
                    <span className="font-medium">actual_total_sot:</span>{' '}
                    {activePreviewRow.actual_total_sot ?? '—'}
                  </div>
                  <div>
                    <span className="font-medium">has_team_stats:</span>{' '}
                    {activePreviewRow.has_team_stats ? 'sì' : 'no'}
                  </div>
                </>
              ) : (
                <div className="text-amber-800 sm:col-span-2">
                  Non in pagina corrente — usa Preview context per i dettagli completi.
                </div>
              )}
            </div>
          </div>
        ) : null}

        {pitFixtures.length > 0 ? (
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-slate-600">
                  <th className="px-2 py-1">ID</th>
                  <th className="px-2 py-1">Kickoff</th>
                  <th className="px-2 py-1">Round</th>
                  <th className="px-2 py-1">Match</th>
                  <th className="px-2 py-1">SOT tot</th>
                  <th className="px-2 py-1">Stats</th>
                </tr>
              </thead>
              <tbody>
                {pitFixtures.map((f) => (
                  <tr
                    key={f.fixture_id}
                    className={`cursor-pointer border-b border-slate-100 hover:bg-teal-50 ${
                      selectedFixtureId === f.fixture_id && parseManualFixtureId(manualFixtureId) == null
                        ? 'bg-teal-100/60'
                        : ''
                    }`}
                    onClick={() => {
                      setSelectedFixtureId(f.fixture_id)
                      setManualFixtureId('')
                    }}
                  >
                    <td className="px-2 py-1 font-mono">{f.fixture_id}</td>
                    <td className="px-2 py-1 text-xs">
                      {new Date(f.kickoff_at).toLocaleString('it-IT')}
                    </td>
                    <td className="px-2 py-1 text-xs">{f.round ?? '—'}</td>
                    <td className="px-2 py-1">
                      {f.home_team.name} vs {f.away_team.name}
                    </td>
                    <td className="px-2 py-1">{f.actual_total_sot ?? '—'}</td>
                    <td className="px-2 py-1">{f.has_team_stats ? 'sì' : 'no'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {pitTotal > 0 ? (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-700">
            <span>
              Mostrate {pitShownFrom}–{pitShownTo} di {pitTotal}
            </span>
            <button
              type="button"
              disabled={loadingId !== null || !pitHasPrev}
              onClick={() => void runListFixtures(Math.max(0, pitOffset - pitLimit))}
              className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
            >
              Pagina precedente
            </button>
            <button
              type="button"
              disabled={loadingId !== null || !pitHasNext}
              onClick={() => void runListFixtures(pitOffset + pitLimit)}
              className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
            >
              Pagina successiva
            </button>
          </div>
        ) : null}

        {pitOutcome ? (
          <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${outcomeClass(pitOutcome.kind)}`}>
            <div className="font-semibold">
              {outcomeLabel(pitOutcome.kind)}
              {pitOutcome.httpStatus != null ? ` — HTTP ${pitOutcome.httpStatus}` : ''}
            </div>
            <div className="mt-1">{pitOutcome.message}</div>
          </div>
        ) : null}

        {pitLeakageCritical ? (
          <p className="mt-3 rounded-lg border border-rose-300 bg-rose-100 px-3 py-2 text-sm font-semibold text-rose-900">
            Possibile leakage: latest_fixture_used_at &gt;= cutoff_time
          </p>
        ) : null}

        {pitPreviewJson ? (
          <div className="mt-3 rounded-lg border border-violet-200 bg-violet-50/50 p-3 text-sm text-slate-800">
            <div className="font-medium text-violet-900">
              Preview prediction v2.1 PIT
              {pitPreviewJson.mode === 'historical_official_xi' ? (
                <span className="ml-2 rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-xs text-amber-900">
                  historical_official_xi
                </span>
              ) : null}
            </div>
            <div className="mt-1 grid gap-1 sm:grid-cols-2">
              <div>
                <span className="font-medium">Match:</span> {pitPreviewJson.fixture.home_team} vs{' '}
                {pitPreviewJson.fixture.away_team}
              </div>
              <div>
                <span className="font-medium">Cutoff:</span>{' '}
                {new Date(pitPreviewJson.cutoff_time).toLocaleString('it-IT')}
              </div>
              <div>
                <span className="font-medium">Predetto home SOT:</span>{' '}
                {pitPreviewJson.prediction.home_predicted_sot ?? '—'}
              </div>
              <div>
                <span className="font-medium">Predetto away SOT:</span>{' '}
                {pitPreviewJson.prediction.away_predicted_sot ?? '—'}
              </div>
              <div>
                <span className="font-medium">Predetto totale SOT:</span>{' '}
                {pitPreviewJson.prediction.total_predicted_sot ?? '—'}
              </div>
              <div>
                <span className="font-medium">Reale totale SOT:</span>{' '}
                {pitPreviewJson.actuals_for_scoring.actual_total_sot ?? '—'}
              </div>
              <div>
                <span className="font-medium">Errore totale (abs):</span>{' '}
                {pitPreviewJson.errors.total_abs_error ?? '—'}
              </div>
              <div>
                <span className="font-medium">leakage_guard:</span>{' '}
                {pitPreviewJson.leakage_guard ? 'true' : 'false'}
              </div>
              <div>
                <span className="font-medium">actuals_used_as_input:</span>{' '}
                {String(pitPreviewJson.actuals_used_as_input)}
              </div>
              <div>
                <span className="font-medium">Fallback macro:</span>{' '}
                {pitPreviewJson.fallback_variables.length}
              </div>
              <div>
                <span className="font-medium">Macro neutre:</span> casa{' '}
                {countNeutralMacros(pitPreviewJson.home_trace)}, trasferta{' '}
                {countNeutralMacros(pitPreviewJson.away_trace)}
              </div>
              <div className="sm:col-span-2">
                <span className="font-medium">Split casa/trasferta:</span> casa{' '}
                {findSplitMacro(pitPreviewJson.home_trace)?.macro_index ?? '—'} (
                {findSplitMacro(pitPreviewJson.home_trace)?.status ?? '—'}), trasferta{' '}
                {findSplitMacro(pitPreviewJson.away_trace)?.macro_index ?? '—'} (
                {findSplitMacro(pitPreviewJson.away_trace)?.status ?? '—'})
              </div>
              {pitPreviewJson.mode === 'historical_official_xi' ? (
                <div className="sm:col-span-2">
                  <span className="font-medium">Player layer:</span> casa{' '}
                  {findPlayerLayerMacro(pitPreviewJson.home_trace)?.macro_index ?? '—'} (
                  {findPlayerLayerMacro(pitPreviewJson.home_trace)?.status ?? '—'}), trasferta{' '}
                  {findPlayerLayerMacro(pitPreviewJson.away_trace)?.macro_index ?? '—'} (
                  {findPlayerLayerMacro(pitPreviewJson.away_trace)?.status ?? '—'})
                </div>
              ) : null}
            </div>
            {pitPreviewJson.warnings.length > 0 ? (
              <p className="mt-2 text-xs text-amber-800">
                Warnings: {pitPreviewJson.warnings.join(', ')}
              </p>
            ) : null}
          </div>
        ) : null}

        {pitPreviewJson ? (
          <pre className="max-h-80 overflow-auto rounded-lg border border-violet-200 bg-slate-900 p-3 text-xs text-slate-100">
            {JSON.stringify(pitPreviewJson, null, 2)}
          </pre>
        ) : null}

        {pitJson ? (
          <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-800">
            <div className="grid gap-1 sm:grid-cols-2">
              <div>
                <span className="font-medium">Fixture:</span> #{pitJson.fixture_id}{' '}
                {pitJson.home_team_name} vs {pitJson.away_team_name}
              </div>
              <div>
                <span className="font-medium">Cutoff:</span>{' '}
                {new Date(pitJson.cutoff_time).toLocaleString('it-IT')}
              </div>
              <div>
                <span className="font-medium">Latest prior:</span>{' '}
                {pitJson.latest_fixture_used_at
                  ? new Date(pitJson.latest_fixture_used_at).toLocaleString('it-IT')
                  : '—'}
              </div>
              <div>
                <span className="font-medium">Prior counts:</span> home={pitJson.home_prior_matches_count},
                away={pitJson.away_prior_matches_count}, lega={pitJson.league_prior_matches_count}
              </div>
              <div>
                <span className="font-medium">leakage_guard:</span>{' '}
                {pitJson.leakage_guard ? 'true' : 'false'}
              </div>
              <div>
                <span className="font-medium">actual_total_sot:</span>{' '}
                {pitJson.actuals_for_scoring.actual_total_sot ?? '—'} (actuals_used_as_input=
                {String(pitJson.actuals_used_as_input)})
              </div>
            </div>
            {pitJson.warnings.length > 0 ? (
              <p className="mt-2 text-xs text-amber-800">
                Warnings: {pitJson.warnings.join(', ')}
              </p>
            ) : null}
          </div>
        ) : null}

        {pitJson ? (
          <pre className="mt-3 max-h-80 overflow-auto rounded-lg border border-slate-200 bg-slate-900 p-3 text-xs text-slate-100">
            {JSON.stringify(pitJson, null, 2)}
          </pre>
        ) : null}
      </div>

      <div className="mt-6 border-t border-slate-200 pt-6">
        <h3 className="text-sm font-semibold text-slate-800">Mini-run preview v2.1 PIT (Step F)</h3>
        <p className="mt-1 text-sm text-slate-600">
          Esegue la preview point-in-time su più fixture e calcola metriche aggregate. Non salva
          prediction, picks o metriche.
        </p>
        <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Questa mini-run è read-only: non crea backtest_predictions, non crea picks e non aggiorna
          run. Dopo la mini-run controlla Health Backtest: predictions/picks/metrics devono restare a
          0.
        </p>

        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Limit
            <select
              value={miniRunLimit}
              onChange={(e) => setMiniRunLimit(Number(e.target.value))}
              className="rounded border border-slate-200 px-2 py-1"
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Offset
            <input
              type="number"
              min={0}
              value={miniRunOffset}
              onChange={(e) => setMiniRunOffset(Math.max(0, Number(e.target.value) || 0))}
              className="w-20 rounded border border-slate-200 px-2 py-1 font-mono text-sm"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Giornata esatta
            <input
              type="number"
              min={1}
              value={miniRunRoundNumber}
              onChange={(e) => setMiniRunRoundNumber(e.target.value)}
              placeholder="3"
              className="w-20 rounded border border-slate-200 px-2 py-1 font-mono text-sm"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Mode
            <select
              value={miniRunMode}
              onChange={(e) =>
                setMiniRunMode(e.target.value as 'pre_lineup' | 'historical_official_xi')
              }
              className="rounded border border-slate-200 px-2 py-1"
            >
              <option value="pre_lineup">pre_lineup</option>
              <option value="historical_official_xi">historical_official_xi</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={miniRunIncludeTrace}
              onChange={(e) => setMiniRunIncludeTrace(e.target.checked)}
            />
            Include trace (max 10)
          </label>
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runMiniRunPreview()}
            className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-900 hover:bg-indigo-100 disabled:opacity-50"
          >
            {loadingId === 'mini-run' ? '…' : 'Esegui mini-run preview'}
          </button>
        </div>

        {miniRunMode === 'historical_official_xi' ? (
          <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Modalità Historical Official XI: la macro player_layer usa XI ufficiale storico e prior stats
            giocatore strict PIT. pre_lineup resta neutro su player layer.
          </p>
        ) : null}

        <p className="mt-2 text-xs text-slate-600">
          Usa il numero esatto della giornata. Es. 3 seleziona solo Regular Season - 3, non la 13.
        </p>

        {miniRunOutcome ? (
          <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${outcomeClass(miniRunOutcome.kind)}`}>
            <div className="font-semibold">
              {outcomeLabel(miniRunOutcome.kind)}
              {miniRunOutcome.httpStatus != null ? ` — HTTP ${miniRunOutcome.httpStatus}` : ''}
            </div>
            <div className="mt-1">{miniRunOutcome.message}</div>
          </div>
        ) : null}

        {miniRunJson ? (
          <>
            <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50/50 p-3 text-sm text-slate-800">
              <div className="font-medium text-indigo-900">Sintesi mini-run</div>
              <div className="mt-1 grid gap-1 sm:grid-cols-3">
                <div>
                  <span className="font-medium">Processate / fallite:</span>{' '}
                  {miniRunJson.summary.fixtures_processed} / {miniRunJson.summary.fixtures_failed}
                </div>
                <div>
                  <span className="font-medium">MAE SOT totale partita:</span>{' '}
                  {fmtMetric(miniRunJson.summary.total_mae)}
                </div>
                <div>
                  <span className="font-medium">RMSE SOT totale partita:</span>{' '}
                  {fmtMetric(miniRunJson.summary.total_rmse)}
                </div>
                <div>
                  <span className="font-medium">Bias medio SOT totale partita:</span>{' '}
                  {fmtMetric(miniRunJson.summary.total_bias)}
                </div>
                <div>
                  <span className="font-medium">Media SOT totale previsto / reale:</span>{' '}
                  {fmtMetric(miniRunJson.summary.avg_predicted_total_sot)} /{' '}
                  {fmtMetric(miniRunJson.summary.avg_actual_total_sot)}
                </div>
                <div>
                  <span className="font-medium">Sovrastimate / sottostimate / errori alti:</span>{' '}
                  {miniRunJson.summary.overestimated_count} / {miniRunJson.summary.underestimated_count} /{' '}
                  {miniRunJson.summary.high_error_count}
                </div>
                <div>
                  <span className="font-medium">db_writes:</span> {String(miniRunJson.db_writes)}
                </div>
                <div>
                  <span className="font-medium">order_by:</span> {miniRunJson.selection.order_by}
                </div>
              </div>
            </div>

            {miniRunJson.split_summary ? (
              <div className="mt-2 rounded-lg border border-indigo-100 bg-white p-3 text-sm text-slate-800">
                <div className="font-medium text-indigo-800">Split casa/trasferta (G1)</div>
                <div className="mt-1 grid gap-1 sm:grid-cols-3">
                  <div>
                    <span className="font-medium">Disponibile / parziale / fallback:</span>{' '}
                    {miniRunJson.split_summary.available_count} /{' '}
                    {miniRunJson.split_summary.partial_count} /{' '}
                    {miniRunJson.split_summary.fallback_count}
                  </div>
                  <div>
                    <span className="font-medium">Media split casa:</span>{' '}
                    {fmtMetric(miniRunJson.split_summary.avg_home_split_index, 4)}
                  </div>
                  <div>
                    <span className="font-medium">Media split trasferta:</span>{' '}
                    {fmtMetric(miniRunJson.split_summary.avg_away_split_index, 4)}
                  </div>
                </div>
              </div>
            ) : null}

            {miniRunJson.player_layer_summary ? (
              <div className="mt-2 rounded-lg border border-violet-100 bg-white p-3 text-sm text-slate-800">
                <div className="font-medium text-violet-800">Player layer storico (G2B)</div>
                <div className="mt-1 grid gap-1 sm:grid-cols-3">
                  <div>
                    <span className="font-medium">Disponibile / parziale / fallback:</span>{' '}
                    {miniRunJson.player_layer_summary.available_count} /{' '}
                    {miniRunJson.player_layer_summary.partial_count} /{' '}
                    {miniRunJson.player_layer_summary.fallback_count}
                  </div>
                  <div>
                    <span className="font-medium">Media player layer casa:</span>{' '}
                    {fmtMetric(miniRunJson.player_layer_summary.avg_home_player_layer_index, 4)}
                  </div>
                  <div>
                    <span className="font-medium">Media player layer trasferta:</span>{' '}
                    {fmtMetric(miniRunJson.player_layer_summary.avg_away_player_layer_index, 4)}
                  </div>
                  <div>
                    <span className="font-medium">Media mapping coverage:</span>{' '}
                    {fmtMetric(miniRunJson.player_layer_summary.avg_mapping_coverage_pct, 1)}%
                  </div>
                  <div>
                    <span className="font-medium">Media prior stats coverage:</span>{' '}
                    {fmtMetric(miniRunJson.player_layer_summary.avg_prior_stats_coverage_pct, 1)}%
                  </div>
                </div>
              </div>
            ) : null}

            {miniRunJson.results.some(isPitLeakageCritical) ? (
              <p className="mt-3 rounded-lg border border-rose-300 bg-rose-100 px-3 py-2 text-sm font-semibold text-rose-900">
                Leakage critico su una o più fixture: possible_leakage, leakage_guard=false o
                latest_fixture_used_at &gt;= cutoff_time.
              </p>
            ) : null}

            {miniRunJson.results.length > 0 ? (
              <div className="mt-4 overflow-x-auto">
                <div className="mb-1 text-sm font-medium text-slate-800">Results per fixture</div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">ID</th>
                      <th className="px-2 py-1">Match</th>
                      <th className="px-2 py-1">SOT totale previsto</th>
                      <th className="px-2 py-1">SOT totale reale</th>
                      <th className="px-2 py-1">Errore assoluto totale</th>
                      <th className="px-2 py-1">Storico casa/trasferta</th>
                      <th className="px-2 py-1">Anti-leakage OK</th>
                    </tr>
                  </thead>
                  <tbody>
                    {miniRunJson.results.map((row) => {
                      const leakageCritical = isPitLeakageCritical(row)
                      return (
                      <tr
                        key={row.fixture_id}
                        className={`border-b border-slate-100 ${leakageCritical ? 'bg-rose-50' : ''}`}
                      >
                        <td className="px-2 py-1 font-mono">{row.fixture_id}</td>
                        <td className="px-2 py-1">
                          {row.home_team} vs {row.away_team}
                          {leakageCritical ? (
                            <span className="ml-1 rounded bg-rose-200 px-1 py-0.5 text-[10px] font-bold text-rose-900">
                              LEAKAGE
                            </span>
                          ) : null}
                        </td>
                        <td className="px-2 py-1">{fmtMetric(row.predicted_total_sot, 4)}</td>
                        <td className="px-2 py-1">{row.actual_total_sot ?? '—'}</td>
                        <td className="px-2 py-1">{fmtMetric(row.total_abs_error, 4)}</td>
                        <td className="px-2 py-1">
                          {row.home_prior_matches_count}/{row.away_prior_matches_count}
                        </td>
                        <td className={`px-2 py-1 ${leakageCritical ? 'font-semibold text-rose-800' : ''}`}>
                          {row.leakage_guard ? 'true' : 'false'}
                        </td>
                      </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}

            {miniRunJson.worst_cases.length > 0 ? (
              <div className="mt-4 overflow-x-auto">
                <div className="mb-1 text-sm font-medium text-slate-800">Worst cases</div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">ID</th>
                      <th className="px-2 py-1">Match</th>
                      <th className="px-2 py-1">Pred / Actual</th>
                      <th className="px-2 py-1">Abs err</th>
                      <th className="px-2 py-1">Prior min</th>
                    </tr>
                  </thead>
                  <tbody>
                    {miniRunJson.worst_cases.map((row) => (
                      <tr key={`worst-${row.fixture_id}`} className="border-b border-slate-100">
                        <td className="px-2 py-1 font-mono">{row.fixture_id}</td>
                        <td className="px-2 py-1">
                          {row.home_team} vs {row.away_team}
                        </td>
                        <td className="px-2 py-1">
                          {fmtMetric(row.predicted_total_sot, 2)} / {row.actual_total_sot ?? '—'}
                        </td>
                        <td className="px-2 py-1">{fmtMetric(row.total_abs_error, 4)}</td>
                        <td className="px-2 py-1">
                          {Math.min(row.home_prior_matches_count, row.away_prior_matches_count)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div className="overflow-x-auto">
                <div className="mb-1 text-sm font-medium text-slate-800">Breakdown sample</div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Bucket</th>
                      <th className="px-2 py-1">N</th>
                      <th className="px-2 py-1">MAE</th>
                      <th className="px-2 py-1">Bias</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      [
                        ['early_low_sample', miniRunJson.sample_breakdown.early_low_sample],
                        ['medium_sample', miniRunJson.sample_breakdown.medium_sample],
                        ['stable_sample', miniRunJson.sample_breakdown.stable_sample],
                      ] as const
                    ).map(([key, bucket]) => (
                      <tr key={key} className="border-b border-slate-100">
                        <td className="px-2 py-1">{key}</td>
                        <td className="px-2 py-1">{bucket.fixtures_count}</td>
                        <td className="px-2 py-1">{fmtMetric(bucket.total_mae)}</td>
                        <td className="px-2 py-1">{fmtMetric(bucket.total_bias)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="overflow-x-auto">
                <div className="mb-1 text-sm font-medium text-slate-800">Breakdown actual total</div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Bucket</th>
                      <th className="px-2 py-1">N</th>
                      <th className="px-2 py-1">MAE</th>
                      <th className="px-2 py-1">Bias</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      [
                        ['low_total', miniRunJson.actual_total_breakdown.low_total],
                        ['medium_total', miniRunJson.actual_total_breakdown.medium_total],
                        ['high_total', miniRunJson.actual_total_breakdown.high_total],
                      ] as const
                    ).map(([key, bucket]) => (
                      <tr key={key} className="border-b border-slate-100">
                        <td className="px-2 py-1">{key}</td>
                        <td className="px-2 py-1">{bucket.fixtures_count}</td>
                        <td className="px-2 py-1">{fmtMetric(bucket.total_mae)}</td>
                        <td className="px-2 py-1">{fmtMetric(bucket.total_bias)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <pre className="mt-4 max-h-80 overflow-auto rounded-lg border border-indigo-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(miniRunJson, null, 2)}
            </pre>
          </>
        ) : null}
      </div>

      <div className="mt-6 border-t border-slate-200 pt-6">
        <h3 className="text-sm font-semibold text-slate-800">
          Betting Pick Evaluation preview (Step H)
        </h3>
        <p className="mt-1 text-sm text-slate-600">
          Simula le giocate Over/Under SOT che il modello avrebbe proposto, confrontandole con il
          reale. Read-only: non salva picks o metriche.
        </p>
        <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Nessun ROI reale in questo step: non usiamo quote bookmaker. Solo edge vs linea e esito
          WIN/LOSS.
        </p>

        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Mode
            <select
              value={pickEvalMode}
              onChange={(e) =>
                setPickEvalMode(e.target.value as 'pre_lineup' | 'historical_official_xi')
              }
              className="rounded border border-slate-200 px-2 py-1"
            >
              <option value="pre_lineup">pre_lineup</option>
              <option value="historical_official_xi">historical_official_xi</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Giornata esatta
            <input
              type="number"
              min={1}
              value={pickEvalRoundNumber}
              onChange={(e) => setPickEvalRoundNumber(e.target.value)}
              placeholder="36"
              className="w-20 rounded border border-slate-200 px-2 py-1 font-mono text-sm"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Limit
            <select
              value={pickEvalLimit}
              onChange={(e) => setPickEvalLimit(Number(e.target.value))}
              className="rounded border border-slate-200 px-2 py-1"
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Offset
            <input
              type="number"
              min={0}
              value={pickEvalOffset}
              onChange={(e) => setPickEvalOffset(Math.max(0, Number(e.target.value) || 0))}
              className="w-20 rounded border border-slate-200 px-2 py-1 font-mono text-sm"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Min edge
            <input
              type="text"
              value={pickEvalMinEdge}
              onChange={(e) => setPickEvalMinEdge(e.target.value)}
              className="w-20 rounded border border-slate-200 px-2 py-1 font-mono text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Linee (comma-sep)
            <input
              type="text"
              value={pickEvalLines}
              onChange={(e) => setPickEvalLines(e.target.value)}
              className="w-48 rounded border border-slate-200 px-2 py-1 font-mono text-sm"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={pickEvalIncludeNoPick}
              onChange={(e) => setPickEvalIncludeNoPick(e.target.checked)}
            />
            Include no-pick
          </label>
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runPickEvaluation()}
            className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-900 hover:bg-emerald-100 disabled:opacity-50"
          >
            {loadingId === 'pick-eval' ? '…' : 'Esegui pick evaluation'}
          </button>
        </div>

        {pickEvalOutcome ? (
          <div
            className={`mt-3 rounded-lg border px-3 py-2 text-sm ${outcomeClass(pickEvalOutcome.kind)}`}
          >
            <div className="font-semibold">
              {outcomeLabel(pickEvalOutcome.kind)}
              {pickEvalOutcome.httpStatus != null ? ` — HTTP ${pickEvalOutcome.httpStatus}` : ''}
            </div>
            <div className="mt-1">{pickEvalOutcome.message}</div>
          </div>
        ) : null}

        {pickEvalJson ? (
          <>
            <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/50 p-3 text-sm text-slate-800">
              <div className="font-medium text-emerald-900">Sintesi pick evaluation</div>
              <div className="mt-1 grid gap-1 sm:grid-cols-3">
                <div>
                  <span className="font-medium">Fixture processate / fallite:</span>{' '}
                  {pickEvalJson.summary.fixtures_processed} / {pickEvalJson.summary.fixtures_failed}
                </div>
                <div>
                  <span className="font-medium">Pick proposti / no pick:</span>{' '}
                  {pickEvalJson.summary.pick_opportunities} / {pickEvalJson.summary.no_pick_count}
                </div>
                <div>
                  <span className="font-medium">Win / Loss / Hit rate:</span>{' '}
                  {pickEvalJson.summary.wins} / {pickEvalJson.summary.losses} /{' '}
                  {fmtMetric(pickEvalJson.summary.hit_rate, 1)}%
                </div>
                <div>
                  <span className="font-medium">Over / Under pick:</span>{' '}
                  {pickEvalJson.summary.over_picks_count} / {pickEvalJson.summary.under_picks_count}
                </div>
                <div>
                  <span className="font-medium">Avg edge:</span>{' '}
                  {fmtMetric(pickEvalJson.summary.avg_edge, 4)}
                </div>
                <div>
                  <span className="font-medium">db_writes:</span> {String(pickEvalJson.db_writes)}
                </div>
              </div>
            </div>

            {pickEvalJson.results.length > 0 ? (
              <div className="mt-4 overflow-x-auto">
                <div className="mb-1 text-sm font-medium text-slate-800">Pick results</div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Fixture</th>
                      <th className="px-2 py-1">Match</th>
                      <th className="px-2 py-1">Pred tot</th>
                      <th className="px-2 py-1">Actual tot</th>
                      <th className="px-2 py-1">Pick</th>
                      <th className="px-2 py-1">Linea</th>
                      <th className="px-2 py-1">Edge</th>
                      <th className="px-2 py-1">Confidence</th>
                      <th className="px-2 py-1">Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pickEvalJson.results.map((row) => {
                      const pick = row.recommended_pick
                      return (
                        <tr key={row.fixture_id} className="border-b border-slate-100">
                          <td className="px-2 py-1 font-mono">{row.fixture_id}</td>
                          <td className="px-2 py-1">{row.match}</td>
                          <td className="px-2 py-1">{fmtMetric(row.predicted_total_sot, 2)}</td>
                          <td className="px-2 py-1">{row.actual_total_sot ?? '—'}</td>
                          <td className="px-2 py-1">
                            {pick ? pick.side.toUpperCase() : '—'}
                          </td>
                          <td className="px-2 py-1">{pick ? pick.line : '—'}</td>
                          <td className="px-2 py-1">{pick ? fmtMetric(pick.edge, 4) : '—'}</td>
                          <td className="px-2 py-1">{pick ? pick.confidence : '—'}</td>
                          <td
                            className={`px-2 py-1 uppercase ${pickOutcomeClass(pick?.outcome, row.no_pick)}`}
                          >
                            {row.no_pick ? 'NO PICK' : pick?.outcome ?? '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div className="overflow-x-auto">
                <div className="mb-1 text-sm font-medium text-slate-800">Breakdown per linea</div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Linea</th>
                      <th className="px-2 py-1">Pick</th>
                      <th className="px-2 py-1">W/L</th>
                      <th className="px-2 py-1">Hit%</th>
                      <th className="px-2 py-1">Avg edge</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pickEvalJson.breakdown_by_line.map((b) => (
                      <tr key={b.line} className="border-b border-slate-100">
                        <td className="px-2 py-1">{b.line}</td>
                        <td className="px-2 py-1">{b.picks_count}</td>
                        <td className="px-2 py-1">
                          {b.wins}/{b.losses}
                        </td>
                        <td className="px-2 py-1">{fmtMetric(b.hit_rate, 1)}</td>
                        <td className="px-2 py-1">{fmtMetric(b.avg_edge, 4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="overflow-x-auto">
                <div className="mb-1 text-sm font-medium text-slate-800">Breakdown confidence</div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Confidence</th>
                      <th className="px-2 py-1">Pick</th>
                      <th className="px-2 py-1">W/L</th>
                      <th className="px-2 py-1">Hit%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pickEvalJson.breakdown_by_confidence.map((b) => (
                      <tr key={b.confidence} className="border-b border-slate-100">
                        <td className="px-2 py-1">{b.confidence}</td>
                        <td className="px-2 py-1">{b.picks_count}</td>
                        <td className="px-2 py-1">
                          {b.wins}/{b.losses}
                        </td>
                        <td className="px-2 py-1">{fmtMetric(b.hit_rate, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="overflow-x-auto">
                <div className="mb-1 text-sm font-medium text-slate-800">Breakdown sample bucket</div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Bucket</th>
                      <th className="px-2 py-1">Pick</th>
                      <th className="px-2 py-1">W/L</th>
                      <th className="px-2 py-1">Hit%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pickEvalJson.breakdown_by_sample_bucket.map((b) => (
                      <tr key={b.bucket} className="border-b border-slate-100">
                        <td className="px-2 py-1">{b.bucket}</td>
                        <td className="px-2 py-1">{b.picks_count}</td>
                        <td className="px-2 py-1">
                          {b.wins}/{b.losses}
                        </td>
                        <td className="px-2 py-1">{fmtMetric(b.hit_rate, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="overflow-x-auto">
                <div className="mb-1 text-sm font-medium text-slate-800">
                  Breakdown actual total bucket
                </div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Bucket</th>
                      <th className="px-2 py-1">Pick</th>
                      <th className="px-2 py-1">W/L</th>
                      <th className="px-2 py-1">Hit%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pickEvalJson.breakdown_by_actual_total_bucket.map((b) => (
                      <tr key={b.bucket} className="border-b border-slate-100">
                        <td className="px-2 py-1">{b.bucket}</td>
                        <td className="px-2 py-1">{b.picks_count}</td>
                        <td className="px-2 py-1">
                          {b.wins}/{b.losses}
                        </td>
                        <td className="px-2 py-1">{fmtMetric(b.hit_rate, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <pre className="mt-4 max-h-80 overflow-auto rounded-lg border border-emerald-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(pickEvalJson, null, 2)}
            </pre>
          </>
        ) : null}
      </div>

      <div className="mt-8 rounded-xl border border-teal-200 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-800">
          Historical Official XI Audit (G2A)
        </h3>
        <p className="mt-1 text-xs text-slate-600">
          Controlla se per una fixture/giornata storica abbiamo formazioni ufficiali, panchina,
          indisponibili e mapping giocatori sufficienti per costruire il player layer point-in-time.
          Modalità futura: <span className="font-medium">historical_official_xi</span> (solo audit, non
          prediction).
        </p>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Giornata esatta
            <input
              type="number"
              min={1}
              className="w-28 rounded border border-slate-300 px-2 py-1 text-sm"
              value={g2aRoundNumber}
              onChange={(e) => setG2aRoundNumber(e.target.value)}
              placeholder="15"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Fixture ID manuale
            <input
              type="text"
              className="w-32 rounded border border-slate-300 px-2 py-1 text-sm"
              value={manualFixtureId}
              onChange={(e) => setManualFixtureId(e.target.value)}
              placeholder="146"
            />
          </label>
          <button
            type="button"
            disabled={needsCompetition || loadingId != null}
            className="rounded-lg bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-50"
            onClick={() => void runG2aRoundAudit()}
          >
            Audit giornata
          </button>
          <button
            type="button"
            disabled={needsCompetition || loadingId != null}
            className="rounded-lg border border-teal-300 bg-teal-50 px-3 py-2 text-sm font-medium text-teal-900 hover:bg-teal-100 disabled:opacity-50"
            onClick={() => void runG2aFixtureAudit()}
          >
            Audit fixture
          </button>
        </div>

        {g2aOutcome ? (
          <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${outcomeClass(g2aOutcome.kind)}`}>
            <div className="font-semibold">
              {outcomeLabel(g2aOutcome.kind)}
              {g2aOutcome.httpStatus != null ? ` — HTTP ${g2aOutcome.httpStatus}` : ''}
            </div>
            <div className="mt-1">{g2aOutcome.message}</div>
          </div>
        ) : null}

        {g2aRoundJson ? (
          <>
            <div className="mt-3 rounded-lg border border-teal-200 bg-teal-50/50 p-3 text-sm text-slate-800">
              <div className="font-medium text-teal-900">Sintesi audit giornata {g2aRoundJson.round_number}</div>
              <div className="mt-1 grid gap-1 sm:grid-cols-3">
                <div>
                  <span className="font-medium">Fixture processate:</span>{' '}
                  {g2aRoundJson.summary.fixtures_processed}
                </div>
                <div>
                  <span className="font-medium">XI ufficiale entrambe:</span>{' '}
                  {g2aRoundJson.summary.fixtures_with_official_xi_both_teams}
                </div>
                <div>
                  <span className="font-medium">Parziali / senza lineup:</span>{' '}
                  {g2aRoundJson.summary.fixtures_with_partial_lineup} /{' '}
                  {g2aRoundJson.summary.fixtures_without_lineup}
                </div>
                <div>
                  <span className="font-medium">Mapping medio titolari:</span>{' '}
                  {fmtMetric(g2aRoundJson.summary.avg_mapping_coverage_pct)}%
                </div>
                <div>
                  <span className="font-medium">Copertura stats prior media:</span>{' '}
                  {fmtMetric(g2aRoundJson.summary.avg_player_stats_prior_coverage_pct)}%
                </div>
                <div>
                  <span className="font-medium">Indisponibili / timestamp safe / missing:</span>{' '}
                  {g2aRoundJson.summary.fixtures_with_unavailable_data} /{' '}
                  {g2aRoundJson.summary.timestamp_safe_count} /{' '}
                  {g2aRoundJson.summary.timestamp_missing_count}
                </div>
                <div>
                  <span className="font-medium">db_writes:</span> {String(g2aRoundJson.db_writes)}
                </div>
              </div>
            </div>
            {g2aRoundJson.fixtures.length > 0 ? (
              <div className="mt-3 overflow-x-auto">
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">ID</th>
                      <th className="px-2 py-1">Match</th>
                      <th className="px-2 py-1">XI H</th>
                      <th className="px-2 py-1">XI A</th>
                      <th className="px-2 py-1">Map H%</th>
                      <th className="px-2 py-1">Map A%</th>
                      <th className="px-2 py-1">Prior H%</th>
                      <th className="px-2 py-1">Prior A%</th>
                      <th className="px-2 py-1">Indisp.</th>
                      <th className="px-2 py-1">TS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g2aRoundJson.fixtures.map((row) => (
                      <tr key={row.fixture_id} className="border-b border-slate-100">
                        <td className="px-2 py-1">{row.fixture_id}</td>
                        <td className="px-2 py-1">{row.match}</td>
                        <td className="px-2 py-1">{row.home_has_official_xi ? row.home_starters_count : '—'}</td>
                        <td className="px-2 py-1">{row.away_has_official_xi ? row.away_starters_count : '—'}</td>
                        <td className="px-2 py-1">{fmtMetric(row.home_mapping_coverage_pct)}</td>
                        <td className="px-2 py-1">{fmtMetric(row.away_mapping_coverage_pct)}</td>
                        <td className="px-2 py-1">{fmtMetric(row.home_prior_stats_coverage_pct)}</td>
                        <td className="px-2 py-1">{fmtMetric(row.away_prior_stats_coverage_pct)}</td>
                        <td className="px-2 py-1">{row.unavailable_data_present ? 'sì' : 'no'}</td>
                        <td className="px-2 py-1">{row.source_timestamp_status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <pre className="mt-3 max-h-80 overflow-auto rounded-lg border border-teal-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(g2aRoundJson, null, 2)}
            </pre>
          </>
        ) : null}

        {g2aFixtureJson ? (
          <>
            <div className="mt-3 rounded-lg border border-teal-200 bg-teal-50/50 p-3 text-sm text-slate-800">
              <div className="font-medium text-teal-900">
                Audit fixture #{g2aFixtureJson.fixture_id} — {g2aFixtureJson.home_team} vs{' '}
                {g2aFixtureJson.away_team}
              </div>
              <div className="mt-1 grid gap-1 sm:grid-cols-2">
                <div>
                  <span className="font-medium">Home XI:</span>{' '}
                  {g2aFixtureJson.home.coverage.starters_count} titolari, mapping{' '}
                  {fmtMetric(g2aFixtureJson.home.mapping.mapping_coverage_pct)}%, prior{' '}
                  {fmtMetric(g2aFixtureJson.home.mapping.player_stats_prior_coverage_pct)}%
                </div>
                <div>
                  <span className="font-medium">Away XI:</span>{' '}
                  {g2aFixtureJson.away.coverage.starters_count} titolari, mapping{' '}
                  {fmtMetric(g2aFixtureJson.away.mapping.mapping_coverage_pct)}%, prior{' '}
                  {fmtMetric(g2aFixtureJson.away.mapping.player_stats_prior_coverage_pct)}%
                </div>
                <div>
                  <span className="font-medium">Fonte home:</span>{' '}
                  {g2aFixtureJson.home.coverage.source_table ?? '—'} (
                  {g2aFixtureJson.home.coverage.source_timestamp_status})
                </div>
                <div>
                  <span className="font-medium">Fonte away:</span>{' '}
                  {g2aFixtureJson.away.coverage.source_table ?? '—'} (
                  {g2aFixtureJson.away.coverage.source_timestamp_status})
                </div>
                <div>
                  <span className="font-medium">db_writes:</span> {String(g2aFixtureJson.db_writes)}
                </div>
              </div>
              {g2aFixtureJson.warnings.length > 0 ? (
                <p className="mt-2 text-xs text-amber-800">
                  Warnings: {g2aFixtureJson.warnings.join(', ')}
                </p>
              ) : null}
            </div>
            <pre className="mt-3 max-h-96 overflow-auto rounded-lg border border-teal-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(g2aFixtureJson, null, 2)}
            </pre>
          </>
        ) : null}
      </div>
    </div>
  )
}
