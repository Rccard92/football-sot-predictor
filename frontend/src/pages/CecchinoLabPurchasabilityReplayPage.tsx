import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CecchinoLabShell } from '../components/cecchino-data-lab/CecchinoLabShell'
import {
  getHistoricalPurchasabilityV3ReplayPreflight,
  historicalScanScopeLabel,
  historicalScanStatusLabel,
  listHistoricalScans,
  type HistoricalPurchasabilityV3ReplayPreflight,
  type HistoricalScanRun,
} from '../lib/cecchinoLabApi'

type UiStatus = 'idle' | 'loading_summary' | 'loading_probe' | 'ready' | 'ready_with_warnings' | 'blocked' | 'error'

const MARKET_ORDER = [
  'HOME',
  'DRAW',
  'AWAY',
  'OVER_2_5',
  'UNDER_2_5',
  'ONE_X',
  'X_TWO',
  'ONE_TWO',
] as const

function statusLabel(status: UiStatus | string): string {
  if (status === 'ready') return 'Pronto'
  if (status === 'ready_with_warnings') return 'Pronto con avvisi'
  if (status === 'blocked') return 'Bloccato'
  if (status === 'loading_summary' || status === 'loading_probe') return 'Verifica in corso…'
  if (status === 'error') return 'Errore'
  return 'In attesa'
}

function statusBadgeClass(status: UiStatus | string): string {
  if (status === 'ready') return 'lab-badge-ok'
  if (status === 'ready_with_warnings') return 'lab-badge-warn'
  if (status === 'blocked' || status === 'error') return 'lab-badge-err'
  return 'lab-badge-muted'
}

function formatPreflightError(err: unknown): string {
  const base =
    'Il backend non ha completato la verifica. Nessun dato del Run è stato modificato.'
  if (!(err instanceof Error)) return base
  const msg = err.message || ''
  if (/failed to fetch|networkerror|load failed/i.test(msg)) {
    return `${base} (errore di rete)`
  }
  return `${base}${msg ? ` — ${msg}` : ''}`
}

function PreflightResultView({ data }: { data: HistoricalPurchasabilityV3ReplayPreflight }) {
  const rp = data.resource_profile
  return (
    <div data-testid="preflight-result" style={{ marginTop: '1rem' }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(12rem, 1fr))',
          gap: '0.75rem',
          marginBottom: '1rem',
        }}
      >
        <div>
          <div style={{ color: 'var(--lab-muted)', fontSize: '0.75rem' }}>RUN</div>
          <div data-testid="preflight-run-meta">
            #{data.run.run_id} · {data.run.season_label} · {data.run.run_scope || '—'} ·{' '}
            {data.run.status}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)', fontSize: '0.75rem' }}>COPERTURA</div>
          <div data-testid="preflight-coverage">
            snapshot {data.source_integrity.snapshots_total ?? 0} / eleggibili{' '}
            {data.source_integrity.snapshots_eligible_core ?? 0}
            <br />
            teoriche {data.workload.theoretical_evaluations} · exact{' '}
            {data.workload.exact_replay_ready} · warning {data.workload.ready_with_warning} · non
            replayable {data.workload.not_replayable}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)', fontSize: '0.75rem' }}>QUOTE</div>
          <div data-testid="preflight-quotes">
            reali {data.quote_quality.real} · derivate {data.quote_quality.derived} · n/d{' '}
            {data.quote_quality.unavailable} · incoerenti {data.quote_quality.inconsistent_flags}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)', fontSize: '0.75rem' }}>INTEGRITÀ</div>
          <div data-testid="preflight-integrity">
            hash {data.source_integrity.with_pre_match_hash ?? 0} · lock{' '}
            {data.source_integrity.with_pre_match_lock ?? 0} · lock&lt;KO{' '}
            {data.source_integrity.lock_before_kickoff ?? 0} · duplicati{' '}
            {data.source_integrity.duplicate_market_keys ?? 0}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)', fontSize: '0.75rem' }}>PERFORMANCE</div>
          <div data-testid="preflight-performance">
            ROI reale {data.performance_coverage.real_profit_ready} · sintetico{' '}
            {data.performance_coverage.synthetic_profit_ready} · risultato senza profitto{' '}
            {data.performance_coverage.result_available_but_profit_missing}
          </div>
        </div>
      </div>

      {rp ? (
        <p
          data-testid="preflight-resource-profile"
          style={{ fontSize: '0.85rem', color: 'var(--lab-muted)', marginBottom: '1rem' }}
        >
          Risorse: {rp.duration_ms ?? 0} ms · streamed {rp.market_rows_streamed ?? 0} · max in RAM{' '}
          {rp.max_market_rows_held_in_memory ?? 0} · yield {rp.stream_yield_per ?? 500}
          {rp.resource_budget_exceeded ? ' · budget exceeded' : ''}
        </p>
      ) : null}

      <div className="lab-table-wrap" style={{ marginBottom: '1rem' }}>
        <table className="lab-table" data-testid="preflight-markets-table">
          <thead>
            <tr>
              <th>Mercato</th>
              <th>Eleggibili</th>
              <th>Exact ready</th>
              <th>Warning</th>
              <th>Non replayable</th>
              <th>Quote reali</th>
              <th>Quote derivate</th>
              <th>Performance ready</th>
            </tr>
          </thead>
          <tbody>
            {MARKET_ORDER.map((mk) => {
              const row = data.by_market[mk]
              if (!row) return null
              const perfReady =
                (row.performance_real_ready || 0) + (row.performance_synthetic_ready || 0)
              return (
                <tr key={mk}>
                  <td>{mk}</td>
                  <td>{row.eligible_rows}</td>
                  <td>{row.exact_replay_ready}</td>
                  <td>{row.ready_with_warning}</td>
                  <td>{row.not_replayable}</td>
                  <td>{row.quote_real}</td>
                  <td>{row.quote_derived}</td>
                  <td>{perfReady}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {(data.blockers.length > 0 || data.warnings.length > 0) && (
        <div data-testid="preflight-issues" style={{ marginBottom: '1rem' }}>
          {data.blockers.length > 0 ? (
            <div style={{ marginBottom: '0.5rem' }}>
              <strong>Blockers</strong>
              <ul>
                {data.blockers.map((b) => (
                  <li key={b.code}>
                    {b.code}: {b.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {data.warnings.length > 0 ? (
            <div>
              <strong>Warnings</strong>
              <ul>
                {data.warnings.map((w) => (
                  <li key={w.code}>
                    {w.code}: {w.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}

      <div data-testid="preflight-conclusion" style={{ fontWeight: 600 }}>
        {data.replay_recommendation.can_replay_without_full_scan ? (
          <p style={{ color: 'var(--lab-ok)', margin: 0 }}>
            Il replay V3 può essere eseguito senza ripetere la scansione completa.
          </p>
        ) : (
          <p style={{ color: 'var(--lab-err)', margin: 0 }}>
            Il replay V3 è bloccato per i seguenti motivi.
          </p>
        )}
        <p
          style={{
            margin: '0.4rem 0 0',
            fontWeight: 400,
            color: 'var(--lab-muted)',
            fontSize: '0.9rem',
          }}
          data-testid="preflight-workload-summary"
        >
          Snapshot eleggibili: {data.source_integrity.snapshots_eligible_core ?? 0} · Valutazioni
          teoriche: {data.workload.theoretical_evaluations} · Decisioni familiari:{' '}
          {data.workload.family_decisions_theoretical ?? 0}
        </p>
      </div>

      {data.probe && !data.probe.skipped ? (
        <p data-testid="preflight-probe-summary" style={{ marginTop: '0.75rem', fontSize: '0.9rem' }}>
          Probe: {String(data.probe.snapshots_probed ?? 0)} snapshot · scored{' '}
          {String(data.probe.markets_scored ?? 0)}
        </p>
      ) : null}
    </div>
  )
}

export function CecchinoLabPurchasabilityReplayPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const runIdParam = searchParams.get('run_id')
  const initialRunId = runIdParam && Number.isFinite(Number(runIdParam)) ? Number(runIdParam) : null

  const [runs, setRuns] = useState<HistoricalScanRun[]>([])
  const [runsLoading, setRunsLoading] = useState(true)
  const [runsError, setRunsError] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(initialRunId)
  const [uiStatus, setUiStatus] = useState<UiStatus>('idle')
  const [data, setData] = useState<HistoricalPurchasabilityV3ReplayPreflight | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setRunsLoading(true)
    setRunsError(null)
    void listHistoricalScans()
      .then((list) => {
        if (cancelled) return
        setRuns(list)
        if (initialRunId && list.some((r) => r.id === initialRunId)) {
          setSelectedRunId(initialRunId)
        }
      })
      .catch((err) => {
        if (cancelled) return
        setRunsError(err instanceof Error ? err.message : 'Errore caricamento run')
      })
      .finally(() => {
        if (!cancelled) setRunsLoading(false)
      })
    return () => {
      cancelled = true
    }
    // solo all'apertura
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectedRun = useMemo(
    () => runs.find((r) => r.id === selectedRunId) ?? null,
    [runs, selectedRunId],
  )

  const onSelectRun = (id: number) => {
    setSelectedRunId(id)
    setSearchParams(id > 0 ? { run_id: String(id) } : {})
    setData(null)
    setError(null)
    setUiStatus('idle')
  }

  const runSummary = useCallback(async () => {
    if (!selectedRunId || selectedRunId <= 0) return
    setUiStatus('loading_summary')
    setError(null)
    try {
      const result = await getHistoricalPurchasabilityV3ReplayPreflight(selectedRunId, {
        includeProbe: false,
      })
      setData(result)
      const st = result.status
      if (st === 'ready' || st === 'ready_with_warnings' || st === 'blocked') {
        setUiStatus(st)
      } else {
        setUiStatus('blocked')
      }
    } catch (err) {
      setData(null)
      setError(formatPreflightError(err))
      setUiStatus('error')
    }
  }, [selectedRunId])

  const runProbe = useCallback(async () => {
    if (!selectedRunId || selectedRunId <= 0) return
    setUiStatus('loading_probe')
    setError(null)
    try {
      const result = await getHistoricalPurchasabilityV3ReplayPreflight(selectedRunId, {
        includeProbe: true,
      })
      setData(result)
      const st = result.status
      if (st === 'ready' || st === 'ready_with_warnings' || st === 'blocked') {
        setUiStatus(st)
      } else {
        setUiStatus('blocked')
      }
    } catch (err) {
      setError(formatPreflightError(err))
      setUiStatus('error')
    }
  }, [selectedRunId])

  const displayStatus = data?.status ?? uiStatus
  const summaryDone =
    data != null &&
    (uiStatus === 'ready' || uiStatus === 'ready_with_warnings' || uiStatus === 'blocked')
  const loading = uiStatus === 'loading_summary' || uiStatus === 'loading_probe'

  return (
    <CecchinoLabShell>
      <div
        className="mx-auto max-w-[1100px] p-4 sm:p-6"
        data-testid="purchasability-replay-page"
      >
        <div style={{ marginBottom: '1rem' }}>
          <Link to="/cecchino-lab" className="text-sm text-[var(--lab-cyan)] underline">
            ← Cecchino Lab
          </Link>
        </div>

        <header className="lab-card" style={{ padding: '1.1rem 1.25rem', marginBottom: '1rem' }}>
          <h1 style={{ margin: 0, fontSize: '1.35rem' }}>Replay Acquistabilità</h1>
          <p style={{ margin: '0.45rem 0 0', color: 'var(--lab-muted)', maxWidth: '40rem' }}>
            Verifica se Acquistabilità può essere ricalcolata utilizzando gli snapshot pre-match già
            congelati, senza ripetere la scansione storica.
          </p>
        </header>

        <section className="lab-card" style={{ padding: '1rem 1.1rem', marginBottom: '1rem' }}>
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.05rem' }}>Seleziona Run</h2>
          {runsLoading ? (
            <p style={{ color: 'var(--lab-muted)' }}>Caricamento elenco run…</p>
          ) : null}
          {runsError ? <p style={{ color: 'var(--lab-err)' }}>{runsError}</p> : null}
          <label style={{ display: 'block', marginBottom: '0.75rem' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--lab-muted)' }}>Run storico</span>
            <select
              className="lab-input mt-1 w-full max-w-xl"
              data-testid="purchasability-replay-run-select"
              value={selectedRunId ?? ''}
              onChange={(e) => onSelectRun(Number(e.target.value))}
            >
              <option value="">— scegli un run —</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  #{r.id} · {r.season_label} · {historicalScanStatusLabel(r.status)} ·{' '}
                  {historicalScanScopeLabel(r)}
                  {r.completed_at ? ` · ${r.completed_at.slice(0, 10)}` : ''}
                </option>
              ))}
            </select>
          </label>
          {selectedRun ? (
            <div
              data-testid="purchasability-replay-run-meta"
              style={{ fontSize: '0.9rem', color: 'var(--lab-muted)' }}
            >
              Run ID {selectedRun.id} · stagione {selectedRun.season_label} · stato{' '}
              {historicalScanStatusLabel(selectedRun.status)} · scope{' '}
              {historicalScanScopeLabel(selectedRun)} · completamento{' '}
              {selectedRun.completed_at?.slice(0, 19) || '—'}
            </div>
          ) : null}
        </section>

        <section
          className="lab-card"
          data-testid="purchasability-v3-replay-preflight"
          style={{ padding: '1rem 1.1rem' }}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
            <button
              type="button"
              className="lab-btn"
              data-testid="verify-purchasability-v3-replay"
              disabled={!selectedRunId || loading}
              onClick={() => void runSummary()}
            >
              Verifica disponibilità replay
            </button>
            {summaryDone ? (
              <button
                type="button"
                className="lab-btn"
                data-testid="verify-purchasability-v3-probe"
                disabled={loading}
                onClick={() => void runProbe()}
              >
                Verifica formula su 30 snapshot
              </button>
            ) : null}
            {uiStatus === 'error' ? (
              <button
                type="button"
                className="lab-btn"
                data-testid="retry-purchasability-v3-replay"
                disabled={!selectedRunId || loading}
                onClick={() => void runSummary()}
              >
                Riprova verifica
              </button>
            ) : null}
            {loading ? (
              <span
                data-testid={
                  uiStatus === 'loading_probe' ? 'preflight-loading-probe' : 'preflight-loading'
                }
                style={{ color: 'var(--lab-muted)' }}
              >
                Verifica in corso…
              </span>
            ) : null}
            <span className={statusBadgeClass(displayStatus)} data-testid="preflight-status-badge">
              {statusLabel(displayStatus)}
            </span>
          </div>

          {error ? (
            <p data-testid="preflight-error" style={{ color: 'var(--lab-err)', marginTop: '0.75rem' }}>
              {error}
            </p>
          ) : null}

          {data ? <PreflightResultView data={data} /> : null}
        </section>
      </div>
    </CecchinoLabShell>
  )
}
