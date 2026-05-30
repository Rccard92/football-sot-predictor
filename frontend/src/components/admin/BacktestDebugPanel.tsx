import { useCallback, useEffect, useState } from 'react'
import {
  createBacktestRun,
  fetchBacktestApiRaw,
  getBacktestDebugHealth,
  getBacktestErrorCode,
  getBacktestErrorMessage,
  getBacktestPointInTimeContext,
  getBacktestRun,
  getBacktestSotV21Preview,
  listBacktestDebugFixtures,
  listBacktestRuns,
  postBacktestSotV21MiniRun,
  type BacktestFixtureCandidate,
  type BacktestRunRow,
  type PointInTimeContextResponse,
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
  const [pitMode, setPitMode] = useState<'pre_lineup' | 'post_lineup'>('pre_lineup')
  const [pitOutcome, setPitOutcome] = useState<Outcome | null>(null)
  const [pitJson, setPitJson] = useState<PointInTimeContextResponse | null>(null)
  const [pitPreviewJson, setPitPreviewJson] = useState<SotV21PreviewResponse | null>(null)
  const [pitLeakageCritical, setPitLeakageCritical] = useState(false)

  const [miniRunLimit, setMiniRunLimit] = useState(20)
  const [miniRunOffset, setMiniRunOffset] = useState(0)
  const [miniRunRoundContains, setMiniRunRoundContains] = useState('')
  const [miniRunIncludeTrace, setMiniRunIncludeTrace] = useState(false)
  const [miniRunOutcome, setMiniRunOutcome] = useState<Outcome | null>(null)
  const [miniRunJson, setMiniRunJson] = useState<SotV21MiniRunResponse | null>(null)

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
      const latest = data.latest_fixture_used_at
      const cutoff = data.cutoff_time
      const leakageBad =
        latest != null && cutoff != null && new Date(latest).getTime() >= new Date(cutoff).getTime()
      setPitLeakageCritical(leakageBad)
      const kind: OutcomeKind = leakageBad ? 'error' : 'ok'
      setPitOutcome({
        kind,
        httpStatus: 200,
        message: leakageBad
          ? 'Context caricato ma possibile leakage rilevato (latest >= cutoff).'
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
    if (selectedCompetitionId == null || fixtureId == null || pitMode !== 'pre_lineup') return
    setLoadingId('pit-prediction')
    try {
      const data = await getBacktestSotV21Preview({
        competition_id: selectedCompetitionId,
        fixture_id: fixtureId,
        mode: 'pre_lineup',
      })
      setPitPreviewJson(data)
      const latest = data.latest_fixture_used_at
      const cutoff = data.cutoff_time
      const leakageBad =
        latest != null && cutoff != null && new Date(latest).getTime() >= new Date(cutoff).getTime()
      setPitLeakageCritical(leakageBad)
      const kind: OutcomeKind = leakageBad ? 'error' : 'ok'
      setPitOutcome({
        kind,
        httpStatus: 200,
        message: leakageBad
          ? 'Preview prediction OK ma possibile leakage (latest >= cutoff).'
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
        mode: 'pre_lineup',
        limit: miniRunLimit,
        offset: miniRunOffset,
        round_contains: miniRunRoundContains.trim() || null,
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
  }, [miniRunIncludeTrace, miniRunLimit, miniRunOffset, miniRunRoundContains, selectedCompetitionId])

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
              onChange={(e) => setPitMode(e.target.value as 'pre_lineup' | 'post_lineup')}
              className="rounded border border-slate-200 px-2 py-1"
            >
              <option value="pre_lineup">pre_lineup</option>
              <option value="post_lineup">post_lineup</option>
            </select>
          </label>
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
              pitMode !== 'pre_lineup'
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
            <div className="font-medium text-violet-900">Preview prediction v2.1 PIT</div>
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
            Round contains
            <input
              type="text"
              value={miniRunRoundContains}
              onChange={(e) => setMiniRunRoundContains(e.target.value)}
              placeholder="Regular Season - 15"
              className="w-48 rounded border border-slate-200 px-2 py-1 text-sm"
            />
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
                  <span className="font-medium">total_mae:</span> {fmtMetric(miniRunJson.summary.total_mae)}
                </div>
                <div>
                  <span className="font-medium">total_rmse:</span> {fmtMetric(miniRunJson.summary.total_rmse)}
                </div>
                <div>
                  <span className="font-medium">total_bias:</span> {fmtMetric(miniRunJson.summary.total_bias)}
                </div>
                <div>
                  <span className="font-medium">avg pred / actual:</span>{' '}
                  {fmtMetric(miniRunJson.summary.avg_predicted_total_sot)} /{' '}
                  {fmtMetric(miniRunJson.summary.avg_actual_total_sot)}
                </div>
                <div>
                  <span className="font-medium">over / under / high error:</span>{' '}
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

            {miniRunJson.results.length > 0 ? (
              <div className="mt-4 overflow-x-auto">
                <div className="mb-1 text-sm font-medium text-slate-800">Results per fixture</div>
                <table className="min-w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-2 py-1">ID</th>
                      <th className="px-2 py-1">Match</th>
                      <th className="px-2 py-1">Pred tot</th>
                      <th className="px-2 py-1">Actual tot</th>
                      <th className="px-2 py-1">Abs err</th>
                      <th className="px-2 py-1">Prior H/A</th>
                      <th className="px-2 py-1">Leakage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {miniRunJson.results.map((row) => (
                      <tr key={row.fixture_id} className="border-b border-slate-100">
                        <td className="px-2 py-1 font-mono">{row.fixture_id}</td>
                        <td className="px-2 py-1">
                          {row.home_team} vs {row.away_team}
                        </td>
                        <td className="px-2 py-1">{fmtMetric(row.predicted_total_sot, 4)}</td>
                        <td className="px-2 py-1">{row.actual_total_sot ?? '—'}</td>
                        <td className="px-2 py-1">{fmtMetric(row.total_abs_error, 4)}</td>
                        <td className="px-2 py-1">
                          {row.home_prior_matches_count}/{row.away_prior_matches_count}
                        </td>
                        <td className="px-2 py-1">{row.leakage_guard ? 'true' : 'false'}</td>
                      </tr>
                    ))}
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
    </div>
  )
}
