import { useMemo, useState } from 'react'
import { CURRENT_SIGNAL_FORMULA_VERSION } from '../../../lib/cecchinoSignalsApi'
import {
  DERIVED_REBUILD_CONFIRM_TOKEN,
  historicalRunDerivedRebuild,
  type HistoricalDerivedRebuildResult,
  type HistoricalDerivedRefresh,
} from '../../../lib/cecchinoLabApi'

type Props = {
  runId: number
  derivedRefresh?: HistoricalDerivedRefresh | null
  onApplied?: () => void
}

const MARKET_REGISTRY_COUNT = 19

function shortSha(sha: string | null | undefined): string {
  if (!sha) return '—'
  return sha.slice(0, 10)
}

export function HistoricalRunDerivedRebuild({ runId, derivedRefresh, onApplied }: Props) {
  const [preview, setPreview] = useState<HistoricalDerivedRebuildResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmChecked, setConfirmChecked] = useState(false)
  const [confirmToken, setConfirmToken] = useState('')
  const [applyResult, setApplyResult] = useState<HistoricalDerivedRebuildResult | null>(null)

  const contract = preview?.signal_contract
  const formula =
    contract?.formula_version ||
    preview?.formula_version ||
    CURRENT_SIGNAL_FORMULA_VERSION
  const consensus =
    contract?.consensus_policy_version ||
    preview?.consensus_policy_version ||
    'cecchino_signal_consensus_v1_min_two'
  const refresh = applyResult?.derived_refresh || derivedRefresh || preview?.derived_refresh

  const canApply = useMemo(() => {
    if (!preview || preview.dry_run === false) return false
    if (preview.run_active) return false
    if ((preview.snapshots_rebuildable || 0) <= 0) return false
    if (!confirmChecked) return false
    return confirmToken.trim() === DERIVED_REBUILD_CONFIRM_TOKEN
  }, [preview, confirmChecked, confirmToken])

  async function runPreflight() {
    setLoading(true)
    setError(null)
    setApplyResult(null)
    setConfirmChecked(false)
    setConfirmToken('')
    try {
      const res = await historicalRunDerivedRebuild(runId, { dry_run: true })
      setPreview(res)
    } catch (e) {
      setPreview(null)
      setError(e instanceof Error ? e.message : 'Errore preflight derived rebuild')
    } finally {
      setLoading(false)
    }
  }

  async function runApply() {
    if (!canApply) return
    setApplying(true)
    setError(null)
    try {
      const res = await historicalRunDerivedRebuild(runId, {
        dry_run: false,
        confirm: DERIVED_REBUILD_CONFIRM_TOKEN,
      })
      setApplyResult(res)
      setPreview(res)
      onApplied?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore apply derived rebuild')
    } finally {
      setApplying(false)
    }
  }

  return (
    <section
      data-testid="historical-run-derived-rebuild"
      className="rounded-xl border p-4"
      style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
    >
      <h3 className="mb-1 text-lg font-semibold">Riallineamento derived V3</h3>
      <p className="mb-3 text-sm text-[var(--lab-muted)]">
        Ricostruisce segnali e market results dagli snapshot persistiti, senza API esterne e senza
        riavviare lo scan.
      </p>

      <div
        className="mb-4 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4"
        data-testid="derived-rebuild-meta"
      >
        <div>
          Formula: <span className="font-medium">{formula}</span>
        </div>
        <div>
          Consenso: <span className="font-medium">{consensus}</span>
        </div>
        <div>
          Market registry:{' '}
          <span className="font-medium">
            {preview?.market_registry_count ?? MARKET_REGISTRY_COUNT}
          </span>
        </div>
        <div data-testid="derived-refresh-status">
          Derived refresh:{' '}
          <span className="font-medium">{refresh?.status || 'mai eseguito'}</span>
          {refresh?.applied_at ? (
            <span className="mt-0.5 block text-[var(--lab-muted)]">
              {refresh.applied_at} · {shortSha(refresh.applied_git_commit)}
            </span>
          ) : null}
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-lg px-3 py-1.5 text-sm font-medium"
          style={{ background: 'var(--lab-cyan)', color: '#0b1220' }}
          disabled={loading || applying}
          onClick={() => void runPreflight()}
          data-testid="derived-rebuild-analyze"
        >
          {loading ? 'Analisi…' : 'Analizza riallineamento'}
        </button>
      </div>

      {error ? (
        <p className="mb-3 text-sm text-[var(--lab-err)]" data-testid="derived-rebuild-error">
          {error}
        </p>
      ) : null}

      {preview ? (
        <div className="mb-3 space-y-2 text-sm" data-testid="derived-rebuild-preview">
          <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-4 text-xs">
            <div>Snapshot: {preview.snapshots_found}</div>
            <div>Rebuildable: {preview.snapshots_rebuildable}</div>
            <div>Parziali: {preview.snapshots_partial}</div>
            <div>Bloccati: {preview.snapshots_blocked}</div>
            <div>Segnali: {preview.signals_to_rebuild}</div>
            <div>KPI/market: {preview.kpi_to_rebuild}</div>
            <div>Market rows: {preview.market_results_to_replace}</div>
            <div>API esterne: {preview.external_api_calls}</div>
          </div>
          {Object.keys(preview.missing_inputs_by_reason || {}).length > 0 ? (
            <details className="text-xs text-[var(--lab-muted)]">
              <summary>Motivi blocco / gap</summary>
              <ul className="mt-1 list-inside list-disc">
                {Object.entries(preview.missing_inputs_by_reason).map(([k, v]) => (
                  <li key={k}>
                    {k}: {v}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          {preview.status === 'preview' || preview.dry_run ? (
            <div
              className="mt-3 space-y-2 rounded-lg border p-3"
              style={{ borderColor: 'var(--lab-border)' }}
              data-testid="derived-rebuild-confirm-box"
            >
              <label className="flex items-start gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={confirmChecked}
                  onChange={(e) => setConfirmChecked(e.target.checked)}
                  data-testid="derived-rebuild-confirm-check"
                />
                <span>
                  Confermo il riallineamento V3 (sostituisce solo artifact derived; nessuna
                  scansione completa).
                </span>
              </label>
              <label className="block text-xs">
                Token di conferma
                <input
                  type="text"
                  value={confirmToken}
                  onChange={(e) => setConfirmToken(e.target.value)}
                  placeholder={DERIVED_REBUILD_CONFIRM_TOKEN}
                  className="mt-1 w-full rounded border px-2 py-1 font-mono text-[11px]"
                  style={{
                    borderColor: 'var(--lab-border)',
                    background: 'var(--lab-surface-2)',
                  }}
                  data-testid="derived-rebuild-confirm-token"
                />
              </label>
              <button
                type="button"
                className="rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-40"
                style={{ background: 'var(--lab-warn)', color: '#1a1208' }}
                disabled={!canApply || applying}
                onClick={() => void runApply()}
                data-testid="derived-rebuild-apply"
              >
                {applying ? 'Applicazione…' : 'Applica riallineamento V3'}
              </button>
            </div>
          ) : null}

          {applyResult?.status === 'completed' ? (
            <p className="text-xs" style={{ color: 'var(--lab-ok)' }} data-testid="derived-rebuild-done">
              Completato: {applyResult.snapshots_rebuilt ?? 0} snapshot riallineati · API esterne{' '}
              {applyResult.external_api_calls} · full_scan_restarted={' '}
              {String(applyResult.full_scan_restarted ?? false)}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
