import { useCallback, useState } from 'react'
import {
  getHistoricalPurchasabilityV3ReplayPreflight,
  type HistoricalPurchasabilityV3ReplayPreflight,
} from '../../../lib/cecchinoLabApi'

type Props = { runId: number }

type UiStatus = 'idle' | 'loading' | 'ready' | 'ready_with_warnings' | 'blocked' | 'error'

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
  if (status === 'loading') return 'Verifica in corso…'
  if (status === 'error') return 'Errore'
  return 'In attesa'
}

function statusBadgeClass(status: UiStatus | string): string {
  if (status === 'ready') return 'lab-badge-ok'
  if (status === 'ready_with_warnings') return 'lab-badge-warn'
  if (status === 'blocked' || status === 'error') return 'lab-badge-err'
  return 'lab-badge-muted'
}

export function HistoricalRunPurchasabilityV3ReplayPreflight({ runId }: Props) {
  const [uiStatus, setUiStatus] = useState<UiStatus>('idle')
  const [data, setData] = useState<HistoricalPurchasabilityV3ReplayPreflight | null>(null)
  const [error, setError] = useState<string | null>(null)

  const runCheck = useCallback(
    async (force = false) => {
      if (!force && data && (uiStatus === 'ready' || uiStatus === 'ready_with_warnings' || uiStatus === 'blocked')) {
        return
      }
      setUiStatus('loading')
      setError(null)
      try {
        const result = await getHistoricalPurchasabilityV3ReplayPreflight(runId)
        setData(result)
        const st = result.status
        if (st === 'ready' || st === 'ready_with_warnings' || st === 'blocked') {
          setUiStatus(st)
        } else {
          setUiStatus('blocked')
        }
      } catch (err) {
        setData(null)
        setError(err instanceof Error ? err.message : 'Errore preflight')
        setUiStatus('error')
      }
    },
    [data, runId, uiStatus],
  )

  const displayStatus = data?.status ?? uiStatus

  return (
    <section
      className="lab-card"
      data-testid="purchasability-v3-replay-preflight"
      style={{ padding: '1rem 1.1rem' }}
    >
      <header style={{ marginBottom: '0.75rem' }}>
        <h3 style={{ margin: 0, fontSize: '1.05rem' }}>Replay Acquistabilità</h3>
        <p style={{ margin: '0.35rem 0 0', color: 'var(--lab-muted)', fontSize: '0.9rem', maxWidth: '52rem' }}>
          Verifica se Acquistabilità può essere ricalcolata usando esclusivamente gli snapshot
          pre-match già congelati, senza ripetere la scansione storica.
        </p>
      </header>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
        {uiStatus === 'idle' || uiStatus === 'error' ? (
          <button
            type="button"
            className="lab-btn"
            data-testid="verify-purchasability-v3-replay"
            onClick={() => void runCheck(true)}
          >
            Verifica replay Acquistabilità
          </button>
        ) : null}
        {uiStatus === 'loading' ? (
          <span data-testid="preflight-loading" style={{ color: 'var(--lab-muted)' }}>
            Verifica in corso…
          </span>
        ) : null}
        {data && uiStatus !== 'loading' ? (
          <button
            type="button"
            className="lab-btn"
            data-testid="refresh-purchasability-v3-replay"
            onClick={() => void runCheck(true)}
          >
            Aggiorna verifica
          </button>
        ) : null}
        <span
          className={statusBadgeClass(displayStatus)}
          data-testid="preflight-status-badge"
        >
          {statusLabel(displayStatus)}
        </span>
      </div>

      {error ? (
        <p data-testid="preflight-error" style={{ color: 'var(--lab-err)', marginTop: '0.75rem' }}>
          {error}
        </p>
      ) : null}

      {data ? (
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
              <div style={{ fontSize: '0.8rem', color: 'var(--lab-muted)', marginTop: '0.25rem' }}>
                scan {data.run.source_git_commit?.slice(0, 8) || '—'} · formula{' '}
                {data.formula.runtime_git_commit?.slice(0, 8) || '—'}
              </div>
            </div>
            <div>
              <div style={{ color: 'var(--lab-muted)', fontSize: '0.75rem' }}>COPERTURA</div>
              <div data-testid="preflight-coverage">
                snapshot {data.source_integrity.snapshots_total ?? 0} / eleggibili{' '}
                {data.source_integrity.snapshots_eligible_core ?? 0}
                <br />
                teoriche {data.workload.theoretical_evaluations} · exact{' '}
                {data.workload.exact_replay_ready} · warning {data.workload.ready_with_warning} ·
                non replayable {data.workload.not_replayable}
              </div>
            </div>
            <div>
              <div style={{ color: 'var(--lab-muted)', fontSize: '0.75rem' }}>QUOTE</div>
              <div data-testid="preflight-quotes">
                reali {data.quote_quality.real} · derivate {data.quote_quality.derived} · n/d{' '}
                {data.quote_quality.unavailable} · incoerenti{' '}
                {data.quote_quality.inconsistent_flags}
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
              Snapshot eleggibili: {data.source_integrity.snapshots_eligible_core ?? 0} ·
              Valutazioni teoriche: {data.workload.theoretical_evaluations} · Decisioni familiari:{' '}
              {data.workload.family_decisions_theoretical ?? 0}
            </p>
          </div>
        </div>
      ) : null}
    </section>
  )
}
