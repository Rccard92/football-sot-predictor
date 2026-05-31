import { useCallback, useEffect, useState } from 'react'
import {
  createBacktestRun,
  fetchBacktestApiRaw,
  getBacktestDebugHealth,
  getBacktestErrorCode,
  getBacktestErrorMessage,
  getBacktestHistoricalLineupAuditFixture,
  getBacktestHistoricalLineupAuditRound,
  getBacktestHistoricalUnavailableAudit,
  getBacktestPointInTimeContext,
  getBacktestRun,
  getBacktestSotV21Preview,
  getSportApiFixtureMappingDebug,
  getSportApiUnavailableDebug,
  listBacktestDebugFixtures,
  listBacktestRuns,
  postBacktestSotV21MiniRun,
  postBacktestSotPickEvaluation,
  postSportApiFixtureMappingBackfill,
  postSportApiFixtureMappingSeasonBackfill,
  postSportApiUnavailableBackfill,
  postSportApiUnavailableSeasonBackfill,
  type BacktestFixtureCandidate,
  type BacktestRunRow,
  type HistoricalLineupAuditFixtureResponse,
  type HistoricalLineupAuditRoundResponse,
  type HistoricalUnavailableAuditResponse,
  type PointInTimeContextResponse,
  type SportApiFixtureMappingBackfillResponse,
  type SportApiFixtureMappingDebugResponse,
  type SportApiFixtureMappingSeasonBackfillResponse,
  type SportApiUnavailableBackfillResponse,
  type SportApiUnavailableDebugResponse,
  type SportApiUnavailableSeasonBackfillResponse,
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

function findLineupsMacro(side: PitSideTrace | undefined) {
  return side?.macros?.find((m) => m.key === 'lineups')
}

function findUnavailableMacro(side: PitSideTrace | undefined) {
  return side?.macros?.find((m) => m.key === 'injuries_unavailable')
}

function formatLineupMacroSide(side: PitSideTrace | undefined): string {
  const macro = findLineupsMacro(side)
  if (!macro) return '— (—)'
  const details = macro.details
  const overlap =
    details?.previous_xi_overlap_pct != null
      ? `${details.previous_xi_overlap_pct}%`
      : details?.previous_xi_overlap_count != null
        ? `${details.previous_xi_overlap_count}/11`
        : '—'
  const formation = details?.formation ?? '—'
  return `${macro.macro_index ?? '—'} (${macro.status ?? '—'}, mod ${formation}, cont ${overlap})`
}

function formatUnavailableMacroSide(side: PitSideTrace | undefined): string {
  const macro = findUnavailableMacro(side)
  if (!macro) return '— (—)'
  const details = macro.details as
    | {
        unavailable_count?: number
        important_absences?: { player_name?: string }[]
        reason?: string
        unavailable_macro_detail?: {
          records_count?: number
          important_absences_count?: number
        }
      }
    | undefined
  const macroDetail = details?.unavailable_macro_detail
  const count =
    macroDetail?.records_count ?? details?.unavailable_count ?? 0
  const important =
    macroDetail?.important_absences_count ??
    details?.important_absences?.length ??
    0
  const reason = details?.reason === 'no_unavailable_players_for_fixture' ? 'nessuno' : `${important} importanti`
  return `${macro.macro_index ?? '—'} (${macro.status ?? '—'}, indisp ${count}, ${reason})`
}

type UnavailableMacroPlayerDetailRow = {
  player_name?: string
  mapping_status?: string
  importance_reason?: string
  impact_score?: number | null
  is_important_absence?: boolean
  status?: string
}

function getUnavailableMacroPlayers(side: PitSideTrace | undefined): UnavailableMacroPlayerDetailRow[] {
  const macro = findUnavailableMacro(side)
  const detail = macro?.details as
    | { unavailable_macro_detail?: { players?: UnavailableMacroPlayerDetailRow[] } }
    | undefined
  return detail?.unavailable_macro_detail?.players ?? []
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

function adviceClass(label: string | null | undefined): string {
  if (label === 'GIOCA') return 'font-semibold text-emerald-700'
  if (label === 'BORDERLINE') return 'font-semibold text-amber-700'
  return 'text-slate-500'
}

function formatAdviceReasons(reasons: string[] | undefined): string {
  if (!reasons || reasons.length === 0) return '—'
  return reasons.slice(0, 2).join(', ')
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
  const [pickEvalCautiousThreshold, setPickEvalCautiousThreshold] = useState('0.75')
  const [pickEvalLines, setPickEvalLines] = useState('4.5,5.5,6.5,7.5,8.5,9.5,10.5,11.5')
  const [pickEvalIncludeNoPick, setPickEvalIncludeNoPick] = useState(true)
  const [pickEvalAdviceFiltersOpen, setPickEvalAdviceFiltersOpen] = useState(false)
  const [pickEvalMinPriorMatches, setPickEvalMinPriorMatches] = useState('10')
  const [pickEvalMinAggEdge, setPickEvalMinAggEdge] = useState('0.25')
  const [pickEvalMinCautEdge, setPickEvalMinCautEdge] = useState('1.00')
  const [pickEvalMaxWarnings, setPickEvalMaxWarnings] = useState('6')
  const [pickEvalAllowEarlySample, setPickEvalAllowEarlySample] = useState(false)
  const [pickEvalAllowLowConfidence, setPickEvalAllowLowConfidence] = useState(false)
  const [pickEvalIncludeBorderline, setPickEvalIncludeBorderline] = useState(false)
  const [pickEvalOutcome, setPickEvalOutcome] = useState<Outcome | null>(null)
  const [pickEvalJson, setPickEvalJson] = useState<SotPickEvaluationResponse | null>(null)

  const [g2aRoundNumber, setG2aRoundNumber] = useState('')
  const [g2aOutcome, setG2aOutcome] = useState<Outcome | null>(null)
  const [g2aFixtureJson, setG2aFixtureJson] = useState<HistoricalLineupAuditFixtureResponse | null>(null)
  const [g2aRoundJson, setG2aRoundJson] = useState<HistoricalLineupAuditRoundResponse | null>(null)

  const [jk1RoundNumber, setJk1RoundNumber] = useState('')
  const [jk1Limit, setJk1Limit] = useState(50)
  const [jk1Offset, setJk1Offset] = useState(0)
  const [jk1Outcome, setJk1Outcome] = useState<Outcome | null>(null)
  const [jk1AuditJson, setJk1AuditJson] = useState<HistoricalUnavailableAuditResponse | null>(null)

  const [k3Limit, setK3Limit] = useState(50)
  const [k3Offset, setK3Offset] = useState(0)
  const [k3RoundNumber, setK3RoundNumber] = useState('')
  const [k3FixtureId, setK3FixtureId] = useState('')
  const [k3DryRun, setK3DryRun] = useState(true)
  const [k3ForceRefresh, setK3ForceRefresh] = useState(false)
  const [k3Outcome, setK3Outcome] = useState<Outcome | null>(null)
  const [k3DebugJson, setK3DebugJson] = useState<SportApiFixtureMappingDebugResponse | null>(null)
  const [k3BackfillJson, setK3BackfillJson] = useState<SportApiFixtureMappingBackfillResponse | null>(null)
  const [k3SeasonBackfillJson, setK3SeasonBackfillJson] =
    useState<SportApiFixtureMappingSeasonBackfillResponse | null>(null)
  const [k2Limit, setK2Limit] = useState(50)
  const [k2Offset, setK2Offset] = useState(0)
  const [k2RoundNumber, setK2RoundNumber] = useState('')
  const [k2FixtureId, setK2FixtureId] = useState('')
  const [k2DryRun, setK2DryRun] = useState(true)
  const [k2ForceRefresh, setK2ForceRefresh] = useState(false)
  const [k2Outcome, setK2Outcome] = useState<Outcome | null>(null)
  const [k2DebugJson, setK2DebugJson] = useState<SportApiUnavailableDebugResponse | null>(null)
  const [k2BackfillJson, setK2BackfillJson] = useState<SportApiUnavailableBackfillResponse | null>(null)
  const [k2SeasonBackfillJson, setK2SeasonBackfillJson] =
    useState<SportApiUnavailableSeasonBackfillResponse | null>(null)

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
    const cautiousThreshold = parseFloat(pickEvalCautiousThreshold)
    if (!Number.isFinite(cautiousThreshold) || cautiousThreshold < 0) {
      setPickEvalOutcome({
        kind: 'error',
        httpStatus: null,
        message: 'Soglia discesa cauta non valida.',
      })
      return
    }
    const minPriorMatches = parseInt(pickEvalMinPriorMatches, 10)
    const minAggEdge = parseFloat(pickEvalMinAggEdge)
    const minCautEdge = parseFloat(pickEvalMinCautEdge)
    const maxWarnings = parseInt(pickEvalMaxWarnings, 10)
    if (
      !Number.isFinite(minPriorMatches) ||
      minPriorMatches < 0 ||
      !Number.isFinite(minAggEdge) ||
      minAggEdge < 0 ||
      !Number.isFinite(minCautEdge) ||
      minCautEdge < 0 ||
      !Number.isFinite(maxWarnings) ||
      maxWarnings < 0
    ) {
      setPickEvalOutcome({
        kind: 'error',
        httpStatus: null,
        message: 'Filtri consiglio giocata non validi.',
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
        cautious_drop_threshold: cautiousThreshold,
        include_no_pick: pickEvalIncludeNoPick,
        min_prior_matches_for_play: minPriorMatches,
        min_aggressive_edge_for_play: minAggEdge,
        min_cautious_edge_for_play: minCautEdge,
        max_warnings_for_play: maxWarnings,
        allow_early_low_sample: pickEvalAllowEarlySample,
        allow_low_confidence: pickEvalAllowLowConfidence,
        include_borderline_as_playable: pickEvalIncludeBorderline,
      })
      setPickEvalJson(data)
      const kind: OutcomeKind =
        data.status === 'ok' || data.status === 'partial_ok' ? 'ok' : 'error'
      const calc = data.calculated_summary
      const adv = data.advised_summary
      setPickEvalOutcome({
        kind,
        httpStatus: 200,
        message: `Pick evaluation — calc agg ${calc.aggressive_calculated_count} / caut ${calc.cautious_calculated_count}, advised play agg ${adv.aggressive_play_count} / caut ${adv.cautious_play_count}, db_writes=${String(data.db_writes)}`,
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
    pickEvalAllowEarlySample,
    pickEvalAllowLowConfidence,
    pickEvalIncludeBorderline,
    pickEvalIncludeNoPick,
    pickEvalLimit,
    pickEvalLines,
    pickEvalMaxWarnings,
    pickEvalMinAggEdge,
    pickEvalMinCautEdge,
    pickEvalMinPriorMatches,
    pickEvalCautiousThreshold,
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

  const runJk1UnavailableAudit = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('jk1-audit')
    try {
      const roundNum = parseMiniRunRoundNumber(jk1RoundNumber)
      const data = await getBacktestHistoricalUnavailableAudit({
        competition_id: selectedCompetitionId,
        round_number: roundNum ?? undefined,
        limit: jk1Limit,
        offset: jk1Offset,
      })
      setJk1AuditJson(data)
      setJk1Outcome({
        kind: 'ok',
        httpStatus: 200,
        message: `Audit indisponibili — scanned ${data.fixtures_scanned}, with_unavailable ${data.fixtures_with_unavailable}, verdict=${data.verdict}, db_writes=${String(data.db_writes)}`,
      })
    } catch (e) {
      setJk1AuditJson(null)
      setJk1Outcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Audit indisponibili JK.1'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [jk1Limit, jk1Offset, jk1RoundNumber, selectedCompetitionId])

  const runK3FixtureDebug = useCallback(async () => {
    if (selectedCompetitionId == null) return
    const fixtureId = parseManualFixtureId(k3FixtureId) ?? resolvePreviewFixtureId()
    if (fixtureId == null) {
      setK3Outcome({ kind: 'error', httpStatus: null, message: 'Inserisci o seleziona un fixture_id.' })
      return
    }
    setLoadingId('k3-debug')
    try {
      const data = await getSportApiFixtureMappingDebug({
        fixture_id: fixtureId,
        competition_id: selectedCompetitionId,
        dry_run: k3DryRun,
        force_refresh: k3ForceRefresh,
      })
      setK3DebugJson(data)
      setK3BackfillJson(null)
      setK3SeasonBackfillJson(null)
      setK3Outcome({
        kind: 'ok',
        httpStatus: 200,
        message: `Debug mapping fixture ${fixtureId} — confidence=${data.match_confidence}, candidates=${data.sportapi_candidates.length}, would_write=${String(data.would_write_mapping)}, dry_run=${String(data.dry_run)}`,
      })
    } catch (e) {
      setK3DebugJson(null)
      setK3Outcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Debug SportAPI mapping'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [k3DryRun, k3FixtureId, k3ForceRefresh, resolvePreviewFixtureId, selectedCompetitionId])

  const runK3Backfill = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('k3-backfill')
    try {
      const roundNum = parseMiniRunRoundNumber(k3RoundNumber)
      const fixtureId = parseManualFixtureId(k3FixtureId)
      const data = await postSportApiFixtureMappingBackfill(
        selectedCompetitionId,
        {
          round_number: roundNum ?? undefined,
          fixture_ids: fixtureId != null ? [fixtureId] : undefined,
          dry_run: k3DryRun,
          force_refresh: k3ForceRefresh,
          limit: k3Limit,
          offset: k3Offset,
        },
      )
      setK3BackfillJson(data)
      setK3SeasonBackfillJson(null)
      setK3DebugJson(null)
      setK3Outcome({
        kind: 'ok',
        httpStatus: 200,
        message: `Backfill mapping — processed ${data.fixtures_processed}, high ${data.high_confidence_matches}, written ${data.written_mappings}, existing ${data.existing_mappings}, dry_run=${String(data.dry_run)}`,
      })
    } catch (e) {
      setK3BackfillJson(null)
      setK3Outcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Backfill SportAPI mapping'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [k3DryRun, k3FixtureId, k3ForceRefresh, k3Limit, k3Offset, k3RoundNumber, selectedCompetitionId])

  const runK3SeasonBackfill = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('k3-season-backfill')
    try {
      const data = await postSportApiFixtureMappingSeasonBackfill(selectedCompetitionId, {
        dry_run: k3DryRun,
        force_refresh: k3ForceRefresh,
        only_finished: true,
        limit: k3Limit,
        offset: k3Offset,
      })
      setK3SeasonBackfillJson(data)
      setK3BackfillJson(null)
      setK3DebugJson(null)
      setK3Outcome({
        kind: 'ok',
        httpStatus: 200,
        message: `Backfill mapping stagione — processed ${data.fixtures_processed}/${data.total_candidates}, high ${data.high_confidence_matches}, written ${data.written_mappings}, api_calls ${data.api_calls}, has_more=${String(data.has_more)}, dry_run=${String(data.dry_run)}`,
      })
    } catch (e) {
      setK3SeasonBackfillJson(null)
      setK3Outcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Backfill mapping stagione'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [k3DryRun, k3ForceRefresh, k3Limit, k3Offset, selectedCompetitionId])

  const runK2FixtureDebug = useCallback(async () => {
    if (selectedCompetitionId == null) return
    const fixtureId = parseManualFixtureId(k2FixtureId) ?? resolvePreviewFixtureId()
    if (fixtureId == null) {
      setK2Outcome({ kind: 'error', httpStatus: null, message: 'Inserisci o seleziona un fixture_id.' })
      return
    }
    setLoadingId('k2-debug')
    try {
      const data = await getSportApiUnavailableDebug({
        fixture_id: fixtureId,
        competition_id: selectedCompetitionId,
        dry_run: k2DryRun,
        force_refresh: k2ForceRefresh,
      })
      setK2DebugJson(data)
      setK2BackfillJson(null)
      setK2Outcome({
        kind: 'ok',
        httpStatus: 200,
        message: `Debug fixture ${fixtureId} — found ${data.total_unavailable_found}, would_write ${data.would_write_count}, source=${data.source_fixture_id}, dry_run=${String(data.dry_run)}`,
      })
    } catch (e) {
      setK2DebugJson(null)
      setK2Outcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Debug SportAPI unavailable'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [k2DryRun, k2FixtureId, k2ForceRefresh, resolvePreviewFixtureId, selectedCompetitionId])

  const runK2Backfill = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('k2-backfill')
    try {
      const roundNum = parseMiniRunRoundNumber(k2RoundNumber)
      const fixtureId = parseManualFixtureId(k2FixtureId)
      const data = await postSportApiUnavailableBackfill(
        selectedCompetitionId,
        {
          round_number: roundNum ?? undefined,
          fixture_ids: fixtureId != null ? [fixtureId] : undefined,
          dry_run: k2DryRun,
          force_refresh: k2ForceRefresh,
          limit: k2Limit,
          offset: k2Offset,
        },
      )
      setK2BackfillJson(data)
      setK2SeasonBackfillJson(null)
      setK2DebugJson(null)
      setK2Outcome({
        kind: 'ok',
        httpStatus: 200,
        message: `Backfill — processed ${data.fixtures_processed}, with_mapping ${data.fixtures_with_mapping}, mapping_missing ${data.fixtures_mapping_missing}, found ${data.total_unavailable_found}, written ${data.total_written}, dry_run=${String(data.dry_run)}`,
      })
    } catch (e) {
      setK2BackfillJson(null)
      setK2Outcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Backfill SportAPI unavailable'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [k2DryRun, k2FixtureId, k2ForceRefresh, k2Limit, k2Offset, k2RoundNumber, selectedCompetitionId])

  const runK2SeasonBackfill = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('k2-season-backfill')
    try {
      const data = await postSportApiUnavailableSeasonBackfill(selectedCompetitionId, {
        dry_run: k2DryRun,
        force_refresh: k2ForceRefresh,
        only_finished: true,
        limit: k2Limit,
        offset: k2Offset,
      })
      setK2SeasonBackfillJson(data)
      setK2BackfillJson(null)
      setK2DebugJson(null)
      setK2Outcome({
        kind: 'ok',
        httpStatus: 200,
        message: `Backfill unavailable stagione — processed ${data.fixtures_processed}/${data.total_candidates}, found ${data.total_unavailable_found}, written ${data.total_written}, api_calls ${data.api_calls}, has_more=${String(data.has_more)}, dry_run=${String(data.dry_run)}`,
      })
    } catch (e) {
      setK2SeasonBackfillJson(null)
      setK2Outcome({
        kind: 'error',
        httpStatus: null,
        message: formatNetworkError(e, 'Backfill unavailable stagione'),
      })
    } finally {
      setLoadingId(null)
    }
  }, [k2DryRun, k2ForceRefresh, k2Limit, k2Offset, selectedCompetitionId])

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
              {pitPreviewJson.mode === 'historical_official_xi' ? (
                <div className="sm:col-span-2">
                  <span className="font-medium">Lineups macro (J):</span> casa{' '}
                  {formatLineupMacroSide(pitPreviewJson.home_trace)}, trasferta{' '}
                  {formatLineupMacroSide(pitPreviewJson.away_trace)}
                </div>
              ) : null}
              {pitPreviewJson.mode === 'historical_official_xi' ? (
                <div className="sm:col-span-2">
                  <span className="font-medium">Indisponibili macro (K):</span> casa{' '}
                  {formatUnavailableMacroSide(pitPreviewJson.home_trace)}, trasferta{' '}
                  {formatUnavailableMacroSide(pitPreviewJson.away_trace)}
                </div>
              ) : null}
              {pitPreviewJson.mode === 'historical_official_xi' &&
              (getUnavailableMacroPlayers(pitPreviewJson.home_trace).length > 0 ||
                getUnavailableMacroPlayers(pitPreviewJson.away_trace).length > 0) ? (
                <div className="sm:col-span-2 mt-2 overflow-x-auto">
                  <div className="font-medium text-violet-900">Dettaglio indisponibili (K trace)</div>
                  <table className="mt-1 min-w-full text-left text-xs text-slate-700">
                    <thead className="border-b border-slate-200 bg-slate-50">
                      <tr>
                        <th className="px-2 py-1">Giocatore</th>
                        <th className="px-2 py-1">Side</th>
                        <th className="px-2 py-1">Status</th>
                        <th className="px-2 py-1">Mapping</th>
                        <th className="px-2 py-1">Impact</th>
                        <th className="px-2 py-1">Importante</th>
                        <th className="px-2 py-1">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(['home', 'away'] as const).flatMap((sideKey) => {
                        const sideTrace =
                          sideKey === 'home'
                            ? pitPreviewJson.home_trace
                            : pitPreviewJson.away_trace
                        return getUnavailableMacroPlayers(sideTrace).map((p, idx) => (
                          <tr key={`${sideKey}-${p.player_name}-${idx}`} className="border-b border-slate-100">
                            <td className="px-2 py-1">{p.player_name ?? '—'}</td>
                            <td className="px-2 py-1">{sideKey}</td>
                            <td className="px-2 py-1">{p.status ?? '—'}</td>
                            <td className="px-2 py-1">{p.mapping_status ?? '—'}</td>
                            <td className="px-2 py-1">{p.impact_score ?? '—'}</td>
                            <td className="px-2 py-1">{p.is_important_absence ? 'sì' : 'no'}</td>
                            <td className="px-2 py-1">{p.importance_reason ?? '—'}</td>
                          </tr>
                        ))
                      })}
                    </tbody>
                  </table>
                </div>
              ) : null}
              {pitPreviewJson.mode === 'historical_official_xi' ? (
                <div className="sm:col-span-2">
                  <span className="font-medium">source_fixture_id:</span> lineup H=
                  {pitPreviewJson.source_fixture_id_lineup_home ?? pitPreviewJson.fixture_id}, A=
                  {pitPreviewJson.source_fixture_id_lineup_away ?? pitPreviewJson.fixture_id}; unavail H=
                  {pitPreviewJson.source_fixture_id_unavailable_home ?? pitPreviewJson.fixture_id}, A=
                  {pitPreviewJson.source_fixture_id_unavailable_away ?? pitPreviewJson.fixture_id}
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

        {pitJson?.historical_summary ? (
          <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50/60 p-3 text-sm text-slate-800">
            <div className="font-medium text-indigo-900">
              Historical summary (JK.1) — fixture #{pitJson.historical_summary.source_fixture_id}
            </div>
            <div className="mt-2 grid gap-1 sm:grid-cols-2">
              <div>
                <span className="font-medium">Snapshot:</span> home{' '}
                {pitJson.historical_summary.fixture_snapshot_summary.home_status} (
                {pitJson.historical_summary.fixture_snapshot_summary.home_starters_count} XI), away{' '}
                {pitJson.historical_summary.fixture_snapshot_summary.away_status} (
                {pitJson.historical_summary.fixture_snapshot_summary.away_starters_count} XI)
              </div>
              <div>
                <span className="font-medium">Indisponibili snapshot:</span> H=
                {pitJson.historical_summary.fixture_snapshot_summary.home_unavailable_count} (
                {pitJson.historical_summary.fixture_snapshot_summary.home_unavailable_source}), A=
                {pitJson.historical_summary.fixture_snapshot_summary.away_unavailable_count} (
                {pitJson.historical_summary.fixture_snapshot_summary.away_unavailable_source})
              </div>
              <div>
                <span className="font-medium">Lineup macro:</span> H{' '}
                {fmtMetric(pitJson.historical_summary.home_lineup_macro_index)} (
                {pitJson.historical_summary.home_lineup_macro_status ?? '—'}), A{' '}
                {fmtMetric(pitJson.historical_summary.away_lineup_macro_index)} (
                {pitJson.historical_summary.away_lineup_macro_status ?? '—'})
              </div>
              <div>
                <span className="font-medium">Unavailable macro:</span> H{' '}
                {fmtMetric(pitJson.historical_summary.home_unavailable_macro_index)} (
                {pitJson.historical_summary.home_unavailable_macro_status ?? '—'}), A{' '}
                {fmtMetric(pitJson.historical_summary.away_unavailable_macro_index)} (
                {pitJson.historical_summary.away_unavailable_macro_status ?? '—'})
              </div>
              <div>
                <span className="font-medium">Player layer:</span> H{' '}
                {fmtMetric(pitJson.historical_summary.home_player_layer_index)} (
                {pitJson.historical_summary.home_player_layer_status ?? '—'}), A{' '}
                {fmtMetric(pitJson.historical_summary.away_player_layer_index)} (
                {pitJson.historical_summary.away_player_layer_status ?? '—'})
              </div>
              <div>
                <span className="font-medium">source_fixture_id:</span> lineup H=
                {pitJson.historical_summary.source_fixture_id_lineup_home}, A=
                {pitJson.historical_summary.source_fixture_id_lineup_away}; unavail H=
                {pitJson.historical_summary.source_fixture_id_unavailable_home}, A=
                {pitJson.historical_summary.source_fixture_id_unavailable_away}
              </div>
            </div>
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

            {miniRunJson.lineup_macro_summary ? (
              <div className="mt-2 rounded-lg border border-teal-100 bg-white p-3 text-sm text-slate-800">
                <div className="font-medium text-teal-800">Lineups / formazioni storiche (J)</div>
                <div className="mt-1 grid gap-1 sm:grid-cols-3">
                  <div>
                    <span className="font-medium">Disponibile / parziale / fallback:</span>{' '}
                    {miniRunJson.lineup_macro_summary.available_count} /{' '}
                    {miniRunJson.lineup_macro_summary.partial_count} /{' '}
                    {miniRunJson.lineup_macro_summary.fallback_count}
                  </div>
                  <div>
                    <span className="font-medium">Media lineup macro casa:</span>{' '}
                    {fmtMetric(miniRunJson.lineup_macro_summary.avg_home_lineup_index, 4)}
                  </div>
                  <div>
                    <span className="font-medium">Media lineup macro trasferta:</span>{' '}
                    {fmtMetric(miniRunJson.lineup_macro_summary.avg_away_lineup_index, 4)}
                  </div>
                  <div>
                    <span className="font-medium">Media continuità XI casa:</span>{' '}
                    {fmtMetric(miniRunJson.lineup_macro_summary.avg_home_xi_continuity_pct, 1)}%
                  </div>
                  <div>
                    <span className="font-medium">Media continuità XI trasferta:</span>{' '}
                    {fmtMetric(miniRunJson.lineup_macro_summary.avg_away_xi_continuity_pct, 1)}%
                  </div>
                </div>
              </div>
            ) : null}

            {miniRunJson.unavailable_macro_summary ? (
              <div className="mt-2 rounded-lg border border-rose-100 bg-white p-3 text-sm text-slate-800">
                <div className="font-medium text-rose-800">Indisponibili storici (K)</div>
                <div className="mt-1 grid gap-1 sm:grid-cols-3">
                  <div>
                    <span className="font-medium">Disponibile / parziale / fallback:</span>{' '}
                    {miniRunJson.unavailable_macro_summary.available_count} /{' '}
                    {miniRunJson.unavailable_macro_summary.partial_count} /{' '}
                    {miniRunJson.unavailable_macro_summary.fallback_count}
                  </div>
                  <div>
                    <span className="font-medium">Fixture con indisponibili reali:</span>{' '}
                    {miniRunJson.unavailable_macro_summary.fixtures_with_unavailable}
                  </div>
                  <div>
                    <span className="font-medium">Totale indisponibili:</span>{' '}
                    {miniRunJson.unavailable_macro_summary.total_unavailable_players ?? 0}
                  </div>
                  <div>
                    <span className="font-medium">Mappati / non mappati:</span>{' '}
                    {miniRunJson.unavailable_macro_summary.mapped_unavailable_players ?? 0} /{' '}
                    {miniRunJson.unavailable_macro_summary.unmapped_unavailable_players ?? 0}
                  </div>
                  <div>
                    <span className="font-medium">Assenze importanti (tot / fixture):</span>{' '}
                    {miniRunJson.unavailable_macro_summary.important_absences_count} /{' '}
                    {miniRunJson.unavailable_macro_summary.fixtures_with_important_absences ?? 0}
                  </div>
                  <div>
                    <span className="font-medium">Media indice casa:</span>{' '}
                    {fmtMetric(miniRunJson.unavailable_macro_summary.avg_home_unavailable_index, 4)}
                  </div>
                  <div>
                    <span className="font-medium">Media indice trasferta:</span>{' '}
                    {fmtMetric(miniRunJson.unavailable_macro_summary.avg_away_unavailable_index, 4)}
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
          Betting Pick Evaluation preview (Step H / H.1)
        </h3>
        <p className="mt-1 text-sm text-slate-600">
          Simula le giocate Over SOT (aggressiva + cauta), mostra sempre linee ed esiti, e indica se
          prima del match avrebbe consigliato la giocata. Read-only: non salva picks o metriche.
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
            Soglia discesa cauta
            <input
              type="text"
              value={pickEvalCautiousThreshold}
              onChange={(e) => setPickEvalCautiousThreshold(e.target.value)}
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

        <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/80">
          <button
            type="button"
            onClick={() => setPickEvalAdviceFiltersOpen((v) => !v)}
            className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium text-slate-800"
          >
            Filtri consiglio giocata
            <span className="text-slate-500">{pickEvalAdviceFiltersOpen ? '▾' : '▸'}</span>
          </button>
          {pickEvalAdviceFiltersOpen ? (
            <div className="flex flex-wrap items-end gap-2 border-t border-slate-200 px-3 pb-3 pt-2">
              <label className="flex flex-col gap-1 text-xs text-slate-600">
                Min partite storiche
                <input
                  type="text"
                  value={pickEvalMinPriorMatches}
                  onChange={(e) => setPickEvalMinPriorMatches(e.target.value)}
                  className="w-20 rounded border border-slate-200 px-2 py-1 font-mono text-sm"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-600">
                Min edge aggressiva
                <input
                  type="text"
                  value={pickEvalMinAggEdge}
                  onChange={(e) => setPickEvalMinAggEdge(e.target.value)}
                  className="w-20 rounded border border-slate-200 px-2 py-1 font-mono text-sm"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-600">
                Min edge cauta
                <input
                  type="text"
                  value={pickEvalMinCautEdge}
                  onChange={(e) => setPickEvalMinCautEdge(e.target.value)}
                  className="w-20 rounded border border-slate-200 px-2 py-1 font-mono text-sm"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-600">
                Max warning
                <input
                  type="text"
                  value={pickEvalMaxWarnings}
                  onChange={(e) => setPickEvalMaxWarnings(e.target.value)}
                  className="w-16 rounded border border-slate-200 px-2 py-1 font-mono text-sm"
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={pickEvalAllowEarlySample}
                  onChange={(e) => setPickEvalAllowEarlySample(e.target.checked)}
                />
                Consenti early sample
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={pickEvalAllowLowConfidence}
                  onChange={(e) => setPickEvalAllowLowConfidence(e.target.checked)}
                />
                Consenti low confidence
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={pickEvalIncludeBorderline}
                  onChange={(e) => setPickEvalIncludeBorderline(e.target.checked)}
                />
                Conta borderline come giocabile
              </label>
            </div>
          ) : null}
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
              <div className="font-medium text-emerald-900">Calculated summary (tutte le linee)</div>
              <div className="mt-1 grid gap-1 sm:grid-cols-3">
                <div>
                  <span className="font-medium">Fixture processate / fallite:</span>{' '}
                  {pickEvalJson.calculated_summary.fixtures_processed} /{' '}
                  {pickEvalJson.calculated_summary.fixtures_failed}
                </div>
                <div>
                  <span className="font-medium">Aggressive calc / no pick:</span>{' '}
                  {pickEvalJson.calculated_summary.aggressive_calculated_count} /{' '}
                  {pickEvalJson.calculated_summary.aggressive_no_pick_count}
                </div>
                <div>
                  <span className="font-medium">Aggressive W/L / Hit rate:</span>{' '}
                  {pickEvalJson.calculated_summary.aggressive_wins} /{' '}
                  {pickEvalJson.calculated_summary.aggressive_losses} /{' '}
                  {fmtMetric(pickEvalJson.calculated_summary.aggressive_hit_rate, 1)}%
                </div>
                <div>
                  <span className="font-medium">Cautious calc / no pick:</span>{' '}
                  {pickEvalJson.calculated_summary.cautious_calculated_count} /{' '}
                  {pickEvalJson.calculated_summary.cautious_no_pick_count}
                </div>
                <div>
                  <span className="font-medium">Cautious W/L / Hit rate:</span>{' '}
                  {pickEvalJson.calculated_summary.cautious_wins} /{' '}
                  {pickEvalJson.calculated_summary.cautious_losses} /{' '}
                  {fmtMetric(pickEvalJson.calculated_summary.cautious_hit_rate, 1)}%
                </div>
                <div>
                  <span className="font-medium">db_writes:</span> {String(pickEvalJson.db_writes)}
                </div>
                {pickEvalMode === 'historical_official_xi' && pickEvalJson.results.length > 0 ? (
                  <>
                    <div className="sm:col-span-2">
                      <span className="font-medium">Lineup macro (J):</span>{' '}
                      {pickEvalJson.results.filter((r) => r.home_lineup_macro_status === 'available').length}{' '}
                      fixture con macro available (casa), media index casa{' '}
                      {fmtMetric(
                        pickEvalJson.results.reduce(
                          (acc, r) => acc + (r.home_lineup_macro_index ?? 0),
                          0,
                        ) / pickEvalJson.results.length,
                        4,
                      )}
                    </div>
                    <div className="sm:col-span-2">
                      <span className="font-medium">Indisponibili macro (K):</span> media index casa{' '}
                      {fmtMetric(
                        pickEvalJson.results.reduce(
                          (acc, r) => acc + (r.home_unavailable_macro_index ?? 1),
                          0,
                        ) / pickEvalJson.results.length,
                        4,
                      )}
                      , assenze importanti tot{' '}
                      {pickEvalJson.results.reduce(
                        (acc, r) => acc + (r.unavailable_important_absences_count ?? 0),
                        0,
                      )}
                    </div>
                  </>
                ) : null}
              </div>
            </div>

            <div className="mt-3 rounded-lg border border-blue-200 bg-blue-50/50 p-3 text-sm text-slate-800">
              <div className="font-medium text-blue-900">Advised summary (solo consigliate)</div>
              <div className="mt-1 grid gap-1 sm:grid-cols-3">
                <div>
                  <span className="font-medium">Aggressive play / no play / borderline:</span>{' '}
                  {pickEvalJson.advised_summary.aggressive_play_count} /{' '}
                  {pickEvalJson.advised_summary.aggressive_no_play_count} /{' '}
                  {pickEvalJson.advised_summary.aggressive_borderline_count}
                </div>
                <div>
                  <span className="font-medium">Aggressive play W/L / Hit rate:</span>{' '}
                  {pickEvalJson.advised_summary.aggressive_play_wins} /{' '}
                  {pickEvalJson.advised_summary.aggressive_play_losses} /{' '}
                  {fmtMetric(pickEvalJson.advised_summary.aggressive_play_hit_rate, 1)}%
                </div>
                <div>
                  <span className="font-medium">Cautious play / no play / borderline:</span>{' '}
                  {pickEvalJson.advised_summary.cautious_play_count} /{' '}
                  {pickEvalJson.advised_summary.cautious_no_play_count} /{' '}
                  {pickEvalJson.advised_summary.cautious_borderline_count}
                </div>
                <div>
                  <span className="font-medium">Cautious play W/L / Hit rate:</span>{' '}
                  {pickEvalJson.advised_summary.cautious_play_wins} /{' '}
                  {pickEvalJson.advised_summary.cautious_play_losses} /{' '}
                  {fmtMetric(pickEvalJson.advised_summary.cautious_play_hit_rate, 1)}%
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
                      <th className="px-2 py-1">Agg linea</th>
                      <th className="px-2 py-1">Agg edge</th>
                      <th className="px-2 py-1">Agg consiglio</th>
                      <th className="px-2 py-1">Agg motivo</th>
                      <th className="px-2 py-1">Agg outcome</th>
                      <th className="px-2 py-1">Caut linea</th>
                      <th className="px-2 py-1">Caut edge</th>
                      <th className="px-2 py-1">Caut consiglio</th>
                      <th className="px-2 py-1">Caut motivo</th>
                      <th className="px-2 py-1">Caut outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pickEvalJson.results.map((row) => {
                      const agg = row.aggressive_pick
                      const caut = row.cautious_pick
                      return (
                        <tr key={row.fixture_id} className="border-b border-slate-100">
                          <td className="px-2 py-1 font-mono">{row.fixture_id}</td>
                          <td className="px-2 py-1">{row.match}</td>
                          <td className="px-2 py-1">{fmtMetric(row.predicted_total_sot, 2)}</td>
                          <td className="px-2 py-1">{row.actual_total_sot ?? '—'}</td>
                          <td className="px-2 py-1">
                            {row.no_aggressive_pick ? '—' : agg?.line}
                          </td>
                          <td className="px-2 py-1">
                            {agg ? fmtMetric(agg.edge, 4) : '—'}
                          </td>
                          <td
                            className={`px-2 py-1 ${adviceClass(agg?.play_advice?.play_advice_label)}`}
                          >
                            {row.no_aggressive_pick ? '—' : agg?.play_advice?.play_advice_label ?? '—'}
                          </td>
                          <td className="px-2 py-1 font-mono text-[10px]">
                            {row.no_aggressive_pick
                              ? '—'
                              : formatAdviceReasons(agg?.play_advice?.advice_reasons)}
                          </td>
                          <td
                            className={`px-2 py-1 uppercase ${pickOutcomeClass(agg?.outcome, row.no_aggressive_pick)}`}
                          >
                            {row.no_aggressive_pick ? 'NO PICK' : agg?.outcome ?? '—'}
                          </td>
                          <td className="px-2 py-1">
                            {row.no_cautious_pick ? '—' : caut?.line}
                          </td>
                          <td className="px-2 py-1">
                            {caut ? fmtMetric(caut.edge, 4) : '—'}
                          </td>
                          <td
                            className={`px-2 py-1 ${adviceClass(caut?.play_advice?.play_advice_label)}`}
                          >
                            {row.no_cautious_pick ? '—' : caut?.play_advice?.play_advice_label ?? '—'}
                          </td>
                          <td className="px-2 py-1 font-mono text-[10px]">
                            {row.no_cautious_pick
                              ? '—'
                              : formatAdviceReasons(caut?.play_advice?.advice_reasons)}
                          </td>
                          <td
                            className={`px-2 py-1 uppercase ${pickOutcomeClass(caut?.outcome, row.no_cautious_pick)}`}
                          >
                            {row.no_cautious_pick ? 'NO PICK' : caut?.outcome ?? '—'}
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
                <div className="mb-1 text-sm font-medium text-slate-800">
                  Aggressive — breakdown per linea
                </div>
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
                    {pickEvalJson.aggressive_by_line.map((b) => (
                      <tr key={`agg-${b.line}`} className="border-b border-slate-100">
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
                <div className="mb-1 text-sm font-medium text-slate-800">
                  Cautious — breakdown per linea
                </div>
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
                    {pickEvalJson.cautious_by_line.map((b) => (
                      <tr key={`caut-${b.line}`} className="border-b border-slate-100">
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
                <div className="mb-1 text-sm font-medium text-slate-800">
                  Aggressive — breakdown confidence
                </div>
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
                    {pickEvalJson.aggressive_by_confidence.map((b) => (
                      <tr key={`agg-conf-${b.confidence}`} className="border-b border-slate-100">
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
                <div className="mb-1 text-sm font-medium text-slate-800">
                  Cautious — breakdown confidence
                </div>
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
                    {pickEvalJson.cautious_by_confidence.map((b) => (
                      <tr key={`caut-conf-${b.confidence}`} className="border-b border-slate-100">
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
                <div className="mb-1 text-sm font-medium text-slate-800">
                  Aggressive — breakdown sample bucket
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
                    {pickEvalJson.aggressive_by_sample_bucket.map((b) => (
                      <tr key={`agg-sample-${b.bucket}`} className="border-b border-slate-100">
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
                  Cautious — breakdown sample bucket
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
                    {pickEvalJson.cautious_by_sample_bucket.map((b) => (
                      <tr key={`caut-sample-${b.bucket}`} className="border-b border-slate-100">
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
                  Advised aggressive — breakdown per linea
                </div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Linea</th>
                      <th className="px-2 py-1">Pick</th>
                      <th className="px-2 py-1">W/L</th>
                      <th className="px-2 py-1">Hit%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pickEvalJson.advised_aggressive_by_line.map((b) => (
                      <tr key={`adv-agg-${b.line}`} className="border-b border-slate-100">
                        <td className="px-2 py-1">{b.line}</td>
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
                  Advised cautious — breakdown per linea
                </div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Linea</th>
                      <th className="px-2 py-1">Pick</th>
                      <th className="px-2 py-1">W/L</th>
                      <th className="px-2 py-1">Hit%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pickEvalJson.advised_cautious_by_line.map((b) => (
                      <tr key={`adv-caut-${b.line}`} className="border-b border-slate-100">
                        <td className="px-2 py-1">{b.line}</td>
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
                  Advised aggressive — breakdown confidence
                </div>
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
                    {pickEvalJson.advised_aggressive_by_confidence.map((b) => (
                      <tr key={`adv-agg-conf-${b.confidence}`} className="border-b border-slate-100">
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
                <div className="mb-1 text-sm font-medium text-slate-800">
                  Advised cautious — breakdown confidence
                </div>
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
                    {pickEvalJson.advised_cautious_by_confidence.map((b) => (
                      <tr key={`adv-caut-conf-${b.confidence}`} className="border-b border-slate-100">
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
                <div className="mb-1 text-sm font-medium text-slate-800">
                  Advised aggressive — breakdown sample bucket
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
                    {pickEvalJson.advised_aggressive_by_sample_bucket.map((b) => (
                      <tr key={`adv-agg-sample-${b.bucket}`} className="border-b border-slate-100">
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
                  Advised cautious — breakdown sample bucket
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
                    {pickEvalJson.advised_cautious_by_sample_bucket.map((b) => (
                      <tr key={`adv-caut-sample-${b.bucket}`} className="border-b border-slate-100">
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
                  Aggressive — breakdown actual total bucket (analisi post-match)
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
                    {pickEvalJson.aggressive_by_actual_total_bucket.map((b) => (
                      <tr key={`agg-actual-${b.bucket}`} className="border-b border-slate-100">
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
                  Cautious — breakdown actual total bucket (analisi post-match)
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
                    {pickEvalJson.cautious_by_actual_total_bucket.map((b) => (
                      <tr key={`caut-actual-${b.bucket}`} className="border-b border-slate-100">
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

      <div className="mt-8 rounded-xl border border-violet-200 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-800">
          SportAPI fixture mapping (K.3 / K.4)
        </h3>
        <p className="mt-1 text-xs text-slate-600">
          Prerequisito per K.2 su fixture storiche. Flusso: mapping dry-run → mapping write → unavailable
          dry-run → unavailable write → audit JK.1 → mini-run.
        </p>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Giornata esatta
            <input
              type="number"
              min={1}
              className="w-28 rounded border border-slate-300 px-2 py-1 text-sm"
              value={k3RoundNumber}
              onChange={(e) => setK3RoundNumber(e.target.value)}
              placeholder="36"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Fixture ID (opzionale)
            <input
              type="number"
              min={1}
              className="w-28 rounded border border-slate-300 px-2 py-1 text-sm"
              value={k3FixtureId}
              onChange={(e) => setK3FixtureId(e.target.value)}
              placeholder="359"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Limit
            <input
              type="number"
              min={1}
              max={400}
              className="w-20 rounded border border-slate-300 px-2 py-1 text-sm"
              value={k3Limit}
              onChange={(e) => setK3Limit(Number(e.target.value) || 50)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Offset
            <input
              type="number"
              min={0}
              className="w-20 rounded border border-slate-300 px-2 py-1 text-sm"
              value={k3Offset}
              onChange={(e) => setK3Offset(Number(e.target.value) || 0)}
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={k3DryRun}
              onChange={(e) => setK3DryRun(e.target.checked)}
            />
            Dry-run
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={k3ForceRefresh}
              onChange={(e) => setK3ForceRefresh(e.target.checked)}
            />
            Force refresh
          </label>
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runK3FixtureDebug()}
            className="rounded-lg border border-violet-300 bg-violet-50 px-3 py-2 text-sm font-medium text-violet-900 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingId === 'k3-debug' ? '…' : 'Debug mapping fixture'}
          </button>
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runK3Backfill()}
            className="rounded-lg border border-violet-400 bg-violet-100 px-3 py-2 text-sm font-medium text-violet-950 hover:bg-violet-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingId === 'k3-backfill' ? '…' : 'Backfill mapping giornata'}
          </button>
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runK3SeasonBackfill()}
            className="rounded-lg border border-violet-500 bg-violet-200 px-3 py-2 text-sm font-medium text-violet-950 hover:bg-violet-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingId === 'k3-season-backfill' ? '…' : 'Backfill mapping stagione'}
          </button>
        </div>

        {k3Outcome ? (
          <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${outcomeClass(k3Outcome.kind)}`}>
            <div className="font-semibold">
              {outcomeLabel(k3Outcome.kind)}
              {k3Outcome.httpStatus != null ? ` — HTTP ${k3Outcome.httpStatus}` : ''}
            </div>
            <div className="mt-1">{k3Outcome.message}</div>
          </div>
        ) : null}

        {k3DebugJson ? (
          <div className="mt-3 rounded-lg border border-violet-200 bg-violet-50/50 p-3 text-sm text-slate-800">
            <div className="font-medium text-violet-900">
              Debug mapping fixture #{k3DebugJson.internal_fixture.fixture_id}
            </div>
            <div className="mt-2 grid gap-1 sm:grid-cols-2">
              <div>
                <span className="font-medium">Existing mapping:</span>{' '}
                {k3DebugJson.existing_mapping.found
                  ? `#${k3DebugJson.existing_mapping.provider_fixture_id}`
                  : 'no'}
              </div>
              <div>
                <span className="font-medium">Confidence:</span> {k3DebugJson.match_confidence}
              </div>
              <div>
                <span className="font-medium">Candidates:</span>{' '}
                {k3DebugJson.sportapi_candidates.length}
              </div>
              <div>
                <span className="font-medium">Would write:</span>{' '}
                {String(k3DebugJson.would_write_mapping)}
              </div>
              {k3DebugJson.best_candidate ? (
                <div className="sm:col-span-2">
                  <span className="font-medium">Best:</span> {k3DebugJson.best_candidate.home_team_name}{' '}
                  vs {k3DebugJson.best_candidate.away_team_name} (score=
                  {k3DebugJson.best_candidate.score}, id=
                  {k3DebugJson.best_candidate.provider_event_id})
                </div>
              ) : null}
            </div>
            <pre className="mt-3 max-h-64 overflow-auto rounded-lg border border-violet-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(k3DebugJson, null, 2)}
            </pre>
          </div>
        ) : null}

        {k3BackfillJson ? (
          <div className="mt-3 rounded-lg border border-violet-200 bg-violet-50/50 p-3 text-sm text-slate-800">
            <div className="font-medium text-violet-900">
              Backfill mapping round {k3BackfillJson.round_number ?? '—'} — processed{' '}
              {k3BackfillJson.fixtures_processed}, written {k3BackfillJson.written_mappings}
            </div>
            {k3BackfillJson.items.length > 0 ? (
              <div className="mt-2 overflow-x-auto">
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Fixture</th>
                      <th className="px-2 py-1">Match</th>
                      <th className="px-2 py-1">Confidence</th>
                      <th className="px-2 py-1">would_write_mapping</th>
                      <th className="px-2 py-1">mapping_written</th>
                    </tr>
                  </thead>
                  <tbody>
                    {k3BackfillJson.items.map((row) => (
                      <tr key={row.fixture_id} className="border-b border-slate-100">
                        <td className="px-2 py-1">#{row.fixture_id}</td>
                        <td className="px-2 py-1">
                          {row.home_team} vs {row.away_team}
                        </td>
                        <td className="px-2 py-1">{row.match_confidence}</td>
                        <td className="px-2 py-1">{String(row.would_write_mapping)}</td>
                        <td className="px-2 py-1">{String(row.mapping_written)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <pre className="mt-3 max-h-64 overflow-auto rounded-lg border border-violet-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(k3BackfillJson, null, 2)}
            </pre>
          </div>
        ) : null}

        {k3SeasonBackfillJson ? (
          <div className="mt-3 rounded-lg border border-violet-200 bg-violet-50/50 p-3 text-sm text-slate-800">
            <div className="font-medium text-violet-900">
              Backfill mapping stagione — processed {k3SeasonBackfillJson.fixtures_processed}/
              {k3SeasonBackfillJson.total_candidates}, high {k3SeasonBackfillJson.high_confidence_matches},
              written {k3SeasonBackfillJson.written_mappings}, api_calls {k3SeasonBackfillJson.api_calls}
            </div>
            <pre className="mt-3 max-h-64 overflow-auto rounded-lg border border-violet-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(k3SeasonBackfillJson, null, 2)}
            </pre>
          </div>
        ) : null}
      </div>

      <div className="mt-8 rounded-xl border border-orange-200 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-800">
          SportAPI unavailable backfill (K.2 / K.4)
        </h3>
        <p className="mt-1 text-xs text-slate-600">
          Import bulk indisponibili missingPlayers da SportAPI. Richiede mapping K.3. Flusso completo:
          mapping dry-run → write → unavailable dry-run → write → audit JK.1.
        </p>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Giornata esatta
            <input
              type="number"
              min={1}
              className="w-28 rounded border border-slate-300 px-2 py-1 text-sm"
              value={k2RoundNumber}
              onChange={(e) => setK2RoundNumber(e.target.value)}
              placeholder="36"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Fixture ID (opzionale)
            <input
              type="number"
              min={1}
              className="w-28 rounded border border-slate-300 px-2 py-1 text-sm"
              value={k2FixtureId}
              onChange={(e) => setK2FixtureId(e.target.value)}
              placeholder="359"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Limit
            <input
              type="number"
              min={1}
              max={400}
              className="w-20 rounded border border-slate-300 px-2 py-1 text-sm"
              value={k2Limit}
              onChange={(e) => setK2Limit(Number(e.target.value) || 50)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Offset
            <input
              type="number"
              min={0}
              className="w-20 rounded border border-slate-300 px-2 py-1 text-sm"
              value={k2Offset}
              onChange={(e) => setK2Offset(Number(e.target.value) || 0)}
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={k2DryRun}
              onChange={(e) => setK2DryRun(e.target.checked)}
            />
            Dry-run
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={k2ForceRefresh}
              onChange={(e) => setK2ForceRefresh(e.target.checked)}
            />
            Force refresh
          </label>
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runK2FixtureDebug()}
            className="rounded-lg border border-orange-300 bg-orange-50 px-3 py-2 text-sm font-medium text-orange-900 hover:bg-orange-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingId === 'k2-debug' ? '…' : 'Debug fixture SportAPI'}
          </button>
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runK2Backfill()}
            className="rounded-lg border border-orange-400 bg-orange-100 px-3 py-2 text-sm font-medium text-orange-950 hover:bg-orange-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingId === 'k2-backfill' ? '…' : 'Backfill indisponibili giornata'}
          </button>
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runK2SeasonBackfill()}
            className="rounded-lg border border-orange-500 bg-orange-200 px-3 py-2 text-sm font-medium text-orange-950 hover:bg-orange-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingId === 'k2-season-backfill' ? '…' : 'Backfill indisponibili stagione'}
          </button>
        </div>

        {k2Outcome ? (
          <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${outcomeClass(k2Outcome.kind)}`}>
            <div className="font-semibold">
              {outcomeLabel(k2Outcome.kind)}
              {k2Outcome.httpStatus != null ? ` — HTTP ${k2Outcome.httpStatus}` : ''}
            </div>
            <div className="mt-1">{k2Outcome.message}</div>
          </div>
        ) : null}

        {k2DebugJson ? (
          <div className="mt-3 rounded-lg border border-orange-200 bg-orange-50/50 p-3 text-sm text-slate-800">
            <div className="font-medium text-orange-900">
              Debug fixture #{k2DebugJson.internal_fixture_id} — source_fixture_id=
              {k2DebugJson.source_fixture_id}
            </div>
            <div className="mt-2 grid gap-1 sm:grid-cols-2">
              <div>
                <span className="font-medium">Found:</span> {k2DebugJson.total_unavailable_found} (H=
                {k2DebugJson.home_unavailable_count}, A={k2DebugJson.away_unavailable_count})
              </div>
              <div>
                <span className="font-medium">Would write:</span> {k2DebugJson.would_write_count}
              </div>
              <div>
                <span className="font-medium">Mapping:</span> {k2DebugJson.mapping_status}
              </div>
              <div>
                <span className="font-medium">Data source:</span> {k2DebugJson.data_source}
              </div>
              <div className="sm:col-span-2">
                <span className="font-medium">Detected paths:</span>{' '}
                {k2DebugJson.detected_paths.length > 0
                  ? k2DebugJson.detected_paths.join(', ')
                  : '—'}
              </div>
            </div>
            <pre className="mt-3 max-h-64 overflow-auto rounded-lg border border-orange-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(k2DebugJson, null, 2)}
            </pre>
          </div>
        ) : null}

        {k2BackfillJson ? (
          <div className="mt-3 rounded-lg border border-orange-200 bg-orange-50/50 p-3 text-sm text-slate-800">
            <div className="font-medium text-orange-900">
              Backfill round {k2BackfillJson.round_number ?? '—'} — processed{' '}
              {k2BackfillJson.fixtures_processed}, with_mapping {k2BackfillJson.fixtures_with_mapping},
              mapping_missing {k2BackfillJson.fixtures_mapping_missing}, written{' '}
              {k2BackfillJson.total_written}
            </div>
            {k2BackfillJson.samples.length > 0 ? (
              <div className="mt-2 overflow-x-auto">
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Fixture</th>
                      <th className="px-2 py-1">Match</th>
                      <th className="px-2 py-1">Found</th>
                      <th className="px-2 py-1">Write</th>
                      <th className="px-2 py-1">Mapping</th>
                    </tr>
                  </thead>
                  <tbody>
                    {k2BackfillJson.samples.map((row) => (
                      <tr key={row.fixture_id} className="border-b border-slate-100">
                        <td className="px-2 py-1">#{row.fixture_id}</td>
                        <td className="px-2 py-1">
                          {row.home_team} vs {row.away_team}
                        </td>
                        <td className="px-2 py-1">{row.unavailable_found}</td>
                        <td className="px-2 py-1">
                          {k2BackfillJson.dry_run ? row.would_write : row.written}
                        </td>
                        <td className="px-2 py-1">{row.mapping_status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <pre className="mt-3 max-h-64 overflow-auto rounded-lg border border-orange-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(k2BackfillJson, null, 2)}
            </pre>
          </div>
        ) : null}

        {k2SeasonBackfillJson ? (
          <div className="mt-3 rounded-lg border border-orange-200 bg-orange-50/50 p-3 text-sm text-slate-800">
            <div className="font-medium text-orange-900">
              Backfill unavailable stagione — processed {k2SeasonBackfillJson.fixtures_processed}/
              {k2SeasonBackfillJson.total_candidates}, found {k2SeasonBackfillJson.total_unavailable_found},
              written {k2SeasonBackfillJson.total_written}, paths:{' '}
              {k2SeasonBackfillJson.source_paths_found.join(', ') || '—'}
            </div>
            <pre className="mt-3 max-h-64 overflow-auto rounded-lg border border-orange-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(k2SeasonBackfillJson, null, 2)}
            </pre>
          </div>
        ) : null}
      </div>

      <div className="mt-8 rounded-xl border border-violet-200 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-800">
          Historical unavailable audit (JK.1)
        </h3>
        <p className="mt-1 text-xs text-slate-600">
          Scansiona lo storage (fixture_missing_players, raw_json lineups, raw_payload provider) per
          verificare se esistono indisponibili storici. Nessuna scrittura DB.
        </p>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Giornata esatta (opzionale)
            <input
              type="number"
              min={1}
              className="w-28 rounded border border-slate-300 px-2 py-1 text-sm"
              value={jk1RoundNumber}
              onChange={(e) => setJk1RoundNumber(e.target.value)}
              placeholder="15"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Limit
            <select
              value={jk1Limit}
              onChange={(e) => setJk1Limit(Number(e.target.value))}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Offset
            <input
              type="number"
              min={0}
              className="w-20 rounded border border-slate-300 px-2 py-1 text-sm"
              value={jk1Offset}
              onChange={(e) => setJk1Offset(Number(e.target.value))}
            />
          </label>
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runJk1UnavailableAudit()}
            className="rounded-lg border border-violet-300 bg-violet-50 px-3 py-2 text-sm font-medium text-violet-900 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingId === 'jk1-audit' ? '…' : 'Audit indisponibili'}
          </button>
        </div>

        {jk1Outcome ? (
          <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${outcomeClass(jk1Outcome.kind)}`}>
            <div className="font-semibold">
              {outcomeLabel(jk1Outcome.kind)}
              {jk1Outcome.httpStatus != null ? ` — HTTP ${jk1Outcome.httpStatus}` : ''}
            </div>
            <div className="mt-1">{jk1Outcome.message}</div>
          </div>
        ) : null}

        {jk1AuditJson ? (
          <>
            <div className="mt-3 rounded-lg border border-violet-200 bg-violet-50/50 p-3 text-sm text-slate-800">
              <div className="font-medium text-violet-900">Verdict: {jk1AuditJson.verdict}</div>
              <div className="mt-2 grid gap-1 sm:grid-cols-2">
                <div>
                  <span className="font-medium">Scanned:</span> {jk1AuditJson.fixtures_scanned}
                </div>
                <div>
                  <span className="font-medium">With unavailable:</span>{' '}
                  {jk1AuditJson.fixtures_with_unavailable}
                </div>
                <div>
                  <span className="font-medium">Totali player:</span>{' '}
                  {jk1AuditJson.total_unavailable_players} (injured{' '}
                  {jk1AuditJson.total_injured_players}, suspended{' '}
                  {jk1AuditJson.total_suspended_players})
                </div>
                <div>
                  <span className="font-medium">Used for counts:</span>{' '}
                  {(jk1AuditJson.source_paths_used_for_counts ?? []).length > 0
                    ? (jk1AuditJson.source_paths_used_for_counts ?? []).join(', ')
                    : '—'}
                </div>
                <div>
                  <span className="font-medium">Diagnostic only:</span>{' '}
                  {(jk1AuditJson.source_paths_detected_diagnostic ?? []).length > 0
                    ? (jk1AuditJson.source_paths_detected_diagnostic ?? []).join(', ')
                    : '—'}
                </div>
                <div className="sm:col-span-2">
                  <span className="font-medium">All source paths:</span>{' '}
                  {jk1AuditJson.source_paths_found.length > 0
                    ? jk1AuditJson.source_paths_found.join(', ')
                    : '—'}
                </div>
                <div className="sm:col-span-2">
                  <span className="font-medium">Storage checked:</span>{' '}
                  {jk1AuditJson.storage_checked.join('; ')}
                </div>
                {jk1AuditJson.raw_json_keys_detected.length > 0 ? (
                  <div className="sm:col-span-2">
                    <span className="font-medium">raw_json keys:</span>{' '}
                    {jk1AuditJson.raw_json_keys_detected.join(', ')}
                  </div>
                ) : null}
              </div>
            </div>
            {jk1AuditJson.sample_fixtures_with_unavailable.length > 0 ? (
              <div className="mt-3 overflow-x-auto">
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">Fixture</th>
                      <th className="px-2 py-1">Match</th>
                      <th className="px-2 py-1">H unavail</th>
                      <th className="px-2 py-1">A unavail</th>
                      <th className="px-2 py-1">Used paths</th>
                      <th className="px-2 py-1">Diagnostic</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jk1AuditJson.sample_fixtures_with_unavailable.map((row) => (
                      <tr key={row.fixture_id} className="border-b border-slate-100">
                        <td className="px-2 py-1">#{row.fixture_id}</td>
                        <td className="px-2 py-1">
                          {row.home_team} vs {row.away_team}
                        </td>
                        <td className="px-2 py-1">{row.home_unavailable_count}</td>
                        <td className="px-2 py-1">{row.away_unavailable_count}</td>
                        <td className="px-2 py-1">
                          {(row.source_paths_used_for_counts ?? row.source_paths).join(', ') || '—'}
                        </td>
                        <td className="px-2 py-1">
                          {(row.source_paths_detected_diagnostic ?? []).join(', ') || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <pre className="mt-3 max-h-80 overflow-auto rounded-lg border border-violet-200 bg-slate-900 p-3 text-xs text-slate-100">
              {JSON.stringify(jk1AuditJson, null, 2)}
            </pre>
          </>
        ) : null}
      </div>
    </div>
  )
}
