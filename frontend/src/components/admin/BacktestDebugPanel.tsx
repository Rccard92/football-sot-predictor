import { useCallback, useEffect, useState } from 'react'
import {
  createBacktestRun,
  fetchBacktestApiRaw,
  getBacktestDebugHealth,
  getBacktestErrorCode,
  getBacktestErrorMessage,
  getBacktestPointInTimeContext,
  getBacktestRun,
  listBacktestDebugFixtures,
  listBacktestRuns,
  type BacktestFixtureCandidate,
  type BacktestRunRow,
  type PointInTimeContextResponse,
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
  const [pitMode, setPitMode] = useState<'pre_lineup' | 'post_lineup'>('pre_lineup')
  const [pitOutcome, setPitOutcome] = useState<Outcome | null>(null)
  const [pitJson, setPitJson] = useState<PointInTimeContextResponse | null>(null)
  const [pitLeakageCritical, setPitLeakageCritical] = useState(false)

  const needsCompetition = selectedCompetitionId == null

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

  const runListFixtures = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoadingId('pit-fixtures')
    setPitOutcome(null)
    setPitJson(null)
    setPitLeakageCritical(false)
    try {
      const data = await listBacktestDebugFixtures({
        competition_id: selectedCompetitionId,
        season_year: selectedCompetition?.season,
        limit: 20,
      })
      setPitFixtures(data.items)
      if (data.items.length > 0 && selectedFixtureId == null) {
        setSelectedFixtureId(data.items[0].fixture_id)
      }
      setPitOutcome({
        kind: 'ok',
        httpStatus: 200,
        message: `${data.items.length} fixture storiche (totale ${data.total})`,
      })
    } catch (e) {
      setPitOutcome({ kind: 'error', httpStatus: null, message: formatNetworkError(e, 'Lista fixture') })
    } finally {
      setLoadingId(null)
    }
  }, [selectedCompetition?.season, selectedCompetitionId, selectedFixtureId])

  const runPreviewContext = useCallback(async () => {
    if (selectedCompetitionId == null || selectedFixtureId == null) return
    setLoadingId('pit-preview')
    setPitLeakageCritical(false)
    try {
      const data = await getBacktestPointInTimeContext({
        competition_id: selectedCompetitionId,
        fixture_id: selectedFixtureId,
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
  }, [pitMode, selectedCompetitionId, selectedFixtureId])

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

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={loadingId !== null || needsCompetition}
            onClick={() => void runListFixtures()}
            className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm font-medium text-teal-900 hover:bg-teal-100 disabled:opacity-50"
          >
            {loadingId === 'pit-fixtures' ? '…' : 'Lista fixture storiche'}
          </button>
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
            disabled={loadingId !== null || needsCompetition || selectedFixtureId == null}
            onClick={() => void runPreviewContext()}
            className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm font-medium text-teal-900 hover:bg-teal-100 disabled:opacity-50"
          >
            {loadingId === 'pit-preview' ? '…' : 'Preview context'}
          </button>
        </div>

        {pitFixtures.length > 0 ? (
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-slate-600">
                  <th className="px-2 py-1">ID</th>
                  <th className="px-2 py-1">Kickoff</th>
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
                      selectedFixtureId === f.fixture_id ? 'bg-teal-100/60' : ''
                    }`}
                    onClick={() => setSelectedFixtureId(f.fixture_id)}
                  >
                    <td className="px-2 py-1 font-mono">{f.fixture_id}</td>
                    <td className="px-2 py-1 text-xs">
                      {new Date(f.kickoff_at).toLocaleString('it-IT')}
                    </td>
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
    </div>
  )
}
