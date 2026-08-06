import { useEffect, useState } from 'react'
import {
  GI_HISTORICAL_BENCHMARK_DEFAULT_PILOT_SIZE,
  GI_HISTORICAL_BENCHMARK_DEFAULT_SEED,
  GI_HISTORICAL_BENCHMARK_FULL_CONFIRM,
  GI_HISTORICAL_BENCHMARK_PILOT_CONFIRM,
  GI_HISTORICAL_BENCHMARK_POLL_MS,
  cancelGoalIntensityBenchmarkJob,
  downloadGoalIntensityBenchmarkExport,
  getGoalIntensityBenchmarkJob,
  goalIntensityBenchmarkPreflight,
  isGiHistoricalBenchmarkJobActive,
  listGoalIntensityBenchmarkJobs,
  resumeGoalIntensityBenchmarkJob,
  startGoalIntensityBenchmarkJob,
  type GiHistoricalBenchmarkJob,
  type GiHistoricalBenchmarkPreflight,
} from '../../../lib/cecchinoLabApi'

type Props = {
  runId: number
  runStatus?: string | null
  seasonLabel?: string | null
  snapshotsTotal?: number | null
}

const MODEL_ORDER = [
  'GI_V4_EXPECTED_GOALS',
  'GI_A_STRICT_CORE',
  'GI_B_RECENCY',
  'GI_E_PRIMARY_RECALIBRATED',
  'GI_F_REGULARIZED_PILLARS',
] as const

const MODEL_LABELS: Record<string, string> = {
  GI_V4_EXPECTED_GOALS: 'V4 Expected Goals',
  GI_A_STRICT_CORE: 'GI_A Strict Core',
  GI_B_RECENCY: 'GI_B Recency',
  GI_E_PRIMARY_RECALIBRATED: 'GI_E Primary Recalibrated',
  GI_F_REGULARIZED_PILLARS: 'GI_F Regularized Pillars',
}

function independenceBadge(status: string | null | undefined): {
  label: string
  className: string
} {
  switch (status) {
    case 'external_independent':
      return {
        label: 'External independent',
        className: 'bg-emerald-100 text-emerald-900 border-emerald-300',
      }
    case 'partial_development_overlap':
      return {
        label: 'Partial overlap',
        className: 'bg-amber-100 text-amber-950 border-amber-300',
      }
    case 'full_development_overlap':
      return {
        label: 'Full overlap',
        className: 'bg-rose-100 text-rose-950 border-rose-300',
      }
    default:
      return {
        label: 'Independence unknown',
        className: 'bg-slate-100 text-slate-800 border-slate-300',
      }
  }
}

function isRunCompleted(status: string | null | undefined): boolean {
  return status === 'completed' || status === 'completed_with_warnings'
}

export function HistoricalRunGoalIntensityBenchmark({
  runId,
  runStatus,
  seasonLabel,
  snapshotsTotal,
}: Props) {
  const [preflight, setPreflight] = useState<GiHistoricalBenchmarkPreflight | null>(null)
  const [job, setJob] = useState<GiHistoricalBenchmarkJob | null>(null)
  const [busy, setBusy] = useState<'idle' | 'preflight' | 'pilot' | 'full' | 'cancel' | 'resume' | 'export'>(
    'idle',
  )
  const [error, setError] = useState<string | null>(null)

  const completed = isRunCompleted(runStatus)

  useEffect(() => {
    let cancelled = false
    void listGoalIntensityBenchmarkJobs(runId)
      .then((res) => {
        if (cancelled) return
        const jobs = res.jobs || []
        const latest = jobs[0] || null
        setJob(latest)
      })
      .catch(() => {
        /* silent: sezione non critica al mount */
      })
    return () => {
      cancelled = true
    }
  }, [runId])

  const jobId = job?.id
  const jobStatus = job?.status
  const jobStale = job?.is_stale

  useEffect(() => {
    if (!jobId) return
    const active = isGiHistoricalBenchmarkJobActive(jobStatus) && !jobStale
    if (!active) return
    const id = window.setInterval(() => {
      void getGoalIntensityBenchmarkJob(jobId)
        .then(setJob)
        .catch(() => undefined)
    }, GI_HISTORICAL_BENCHMARK_POLL_MS)
    return () => window.clearInterval(id)
  }, [jobId, jobStatus, jobStale])

  const pilotGateOk = job?.mode === 'pilot' && job?.status === 'completed' && job?.pilot_gate?.ok === true

  const fullEnabled = completed && pilotGateOk && busy === 'idle'

  const pilotDisabled =
    busy !== 'idle' || preflight == null || preflight.pilot_allowed === false

  const ind =
    preflight?.independence ||
    (job?.preflight_json?.independence as GiHistoricalBenchmarkPreflight['independence'] | undefined)
  const badge = independenceBadge(ind?.status || job?.independence_status)
  const summary = (job?.summary_json || {}) as Record<string, unknown>
  const metrics = (summary.metrics || {}) as Record<string, unknown>
  const modelMetrics = (metrics.model_metrics || {}) as Record<string, Record<string, unknown>>
  const pairwise = (metrics.pairwise || []) as Array<Record<string, unknown>>
  const missing = job?.missing_by_reason_json || preflight?.availability?.missing_by_reason || {}

  const showResume = Boolean(job?.can_resume)

  async function runPreflight() {
    setBusy('preflight')
    setError(null)
    try {
      const res = await goalIntensityBenchmarkPreflight(runId)
      setPreflight(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore preflight')
    } finally {
      setBusy('idle')
    }
  }

  async function startPilot() {
    if (pilotDisabled) return
    setBusy('pilot')
    setError(null)
    try {
      const res = await startGoalIntensityBenchmarkJob(runId, {
        mode: 'pilot',
        confirm: GI_HISTORICAL_BENCHMARK_PILOT_CONFIRM,
        pilot_size: GI_HISTORICAL_BENCHMARK_DEFAULT_PILOT_SIZE,
        random_seed: GI_HISTORICAL_BENCHMARK_DEFAULT_SEED,
      })
      setJob(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore avvio pilot')
    } finally {
      setBusy('idle')
    }
  }

  async function startFull() {
    if (!fullEnabled || !job) return
    setBusy('full')
    setError(null)
    try {
      const res = await startGoalIntensityBenchmarkJob(runId, {
        mode: 'full',
        confirm: GI_HISTORICAL_BENCHMARK_FULL_CONFIRM,
        pilot_job_id: job.id,
      })
      setJob(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore avvio full')
    } finally {
      setBusy('idle')
    }
  }

  async function onCancel() {
    if (!job) return
    setBusy('cancel')
    setError(null)
    try {
      setJob(await cancelGoalIntensityBenchmarkJob(job.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore cancel')
    } finally {
      setBusy('idle')
    }
  }

  async function onResume() {
    if (!job) return
    setBusy('resume')
    setError(null)
    try {
      setJob(await resumeGoalIntensityBenchmarkJob(job.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore resume')
    } finally {
      setBusy('idle')
    }
  }

  async function onExport() {
    if (!job) return
    setBusy('export')
    setError(null)
    try {
      const blob = await downloadGoalIntensityBenchmarkExport(job.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `gi-benchmark-job-${job.id}.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore export')
    } finally {
      setBusy('idle')
    }
  }

  if (!completed) {
    return (
      <section
        data-testid="historical-run-gi-benchmark"
        className="rounded-xl border p-4 opacity-70"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <h3 className="text-lg font-semibold">Benchmark Goal Intensity V4 vs V5</h3>
        <p className="mt-1 text-sm text-[var(--lab-muted)]">
          Disponibile solo per run completed. Stato attuale: {runStatus || '—'}.
        </p>
      </section>
    )
  }

  const pf = preflight
  const bundle = pf?.bundle
  const pairedEstimate =
    pf?.paired_complete_estimate ?? pf?.availability?.paired_complete_estimate ?? 0
  const probeN = pf?.five_models_probe_n ?? pf?.availability?.five_models_probe_n ?? 0
  const probeOk = pf?.five_models_probe_ok ?? pf?.availability?.five_models_probe_ok ?? 0

  return (
    <section
      data-testid="historical-run-gi-benchmark"
      className="rounded-xl border p-4"
      style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
    >
      <h3 className="mb-1 text-lg font-semibold">Benchmark Goal Intensity V4 vs V5</h3>
      <p className="mb-4 text-sm text-[var(--lab-muted)]">
        Confronto frozen su bundle v2.1. Nessuna API esterna, nessun refit, nessuna modifica alla run
        originale.
      </p>

      <div className="mb-4 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
        <div data-testid="gi-bench-run-meta">
          <div className="font-medium">RUN</div>
          <div>ID {runId}</div>
          <div>Stagione {seasonLabel || pf?.run?.season || '—'}</div>
          <div>Stato {runStatus}</div>
          <div>Snapshot {snapshotsTotal ?? pf?.run?.snapshots_found ?? '—'}</div>
        </div>
        <div data-testid="gi-bench-bundle-meta">
          <div className="font-medium">BUNDLE</div>
          <div>ID {bundle?.id ?? job?.bundle_id ?? '—'}</div>
          <div className="break-all">Version {bundle?.version ?? 'v2_1'}</div>
          <div className="break-all">Hash {bundle?.definition_hash || '—'}</div>
          <div>Frozen · non operativo live</div>
        </div>
        <div data-testid="gi-bench-independence">
          <div className="font-medium">INDIPENDENZA</div>
          <span
            className={`mt-1 inline-block rounded border px-2 py-0.5 text-[11px] font-medium ${badge.className}`}
            data-testid="gi-bench-independence-badge"
          >
            {badge.label}
          </span>
          <div className="mt-1">
            Overlap {ind?.overlap_count ?? 0} ({ind?.overlap_pct ?? 0}%)
          </div>
          <div className="mt-1 text-[var(--lab-muted)]">
            Label scientifica: {ind?.scientific_label || '—'}
          </div>
        </div>
        <div data-testid="gi-bench-job-meta">
          <div className="font-medium">JOB</div>
          <div>ID {job?.id ?? '—'}</div>
          <div>Mode {job?.mode ?? '—'}</div>
          <div>Status {job?.status ?? '—'}</div>
          {job?.effective_status && job.effective_status !== job.status ? (
            <div data-testid="gi-bench-effective-status">Effective {job.effective_status}</div>
          ) : null}
          <div>
            Progress {job?.progress_pct ?? 0}% · paired {job?.paired_complete ?? 0}
          </div>
        </div>
      </div>

      {(ind?.status === 'partial_development_overlap' ||
        ind?.status === 'full_development_overlap') && (
        <div
          className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950"
          data-testid="gi-bench-overlap-warning"
        >
          Overlap con coorte di sviluppo rilevato: trattare come{' '}
          <strong>historical_diagnostic_replay</strong>, non come external validation.
        </div>
      )}

      {job?.is_stale ? (
        <div
          className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950"
          data-testid="gi-bench-stale-warning"
        >
          Job stale (heartbeat assente o scaduto). Usa Resume per riprendere senza perdere le
          righe già prodotte.
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="gi-bench-preflight"
          onClick={() => void runPreflight()}
          disabled={busy !== 'idle'}
          className="rounded-lg bg-[var(--lab-cyan)] px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy === 'preflight' ? 'Analisi…' : 'Analizza fattibilità'}
        </button>
        <button
          type="button"
          data-testid="gi-bench-pilot"
          onClick={() => void startPilot()}
          disabled={pilotDisabled}
          className="rounded-lg border px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          style={{ borderColor: 'var(--lab-border)' }}
          title={
            pf == null
              ? 'Esegui prima Analizza fattibilità'
              : pf.pilot_allowed === false
                ? 'Pilot non consentito dal preflight'
                : 'Avvia pilot'
          }
        >
          Avvia pilot {GI_HISTORICAL_BENCHMARK_DEFAULT_PILOT_SIZE} partite
        </button>
        <button
          type="button"
          data-testid="gi-bench-full"
          onClick={() => void startFull()}
          disabled={!fullEnabled}
          className="rounded-lg border px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          style={{ borderColor: 'var(--lab-border)' }}
          title={
            fullEnabled
              ? 'Avvia benchmark completo'
              : job?.pilot_gate && job.pilot_gate.ok === false
                ? `Pilot gate fallito: ${(job.pilot_gate.reasons || []).join(', ')}`
                : 'Disponibile solo dopo pilot completed con gate valido'
          }
        >
          Avvia benchmark completo
        </button>
        {job && isGiHistoricalBenchmarkJobActive(job.status) && !job.is_stale ? (
          <button
            type="button"
            data-testid="gi-bench-cancel"
            onClick={() => void onCancel()}
            disabled={busy !== 'idle'}
            className="rounded-lg border border-rose-300 px-3 py-2 text-sm text-rose-800"
          >
            Cancel
          </button>
        ) : null}
        {showResume ? (
          <button
            type="button"
            data-testid="gi-bench-resume"
            onClick={() => void onResume()}
            disabled={busy !== 'idle'}
            className="rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: 'var(--lab-border)' }}
          >
            Resume
          </button>
        ) : null}
        {job && job.status === 'completed' ? (
          <button
            type="button"
            data-testid="gi-bench-export"
            onClick={() => void onExport()}
            disabled={busy !== 'idle'}
            className="rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: 'var(--lab-border)' }}
          >
            Export ZIP
          </button>
        ) : null}
      </div>

      {error ? (
        <p className="mb-3 text-sm text-rose-700" data-testid="gi-bench-error">
          {error}
        </p>
      ) : null}

      {pf ? (
        <div
          className="mb-4 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4"
          data-testid="gi-bench-preflight-panel"
        >
          <div>V4 rebuildable: {pf.availability?.v4_rebuildable ?? 0}</div>
          <div>V5 rebuildable: {pf.availability?.v5_features_rebuildable ?? 0}</div>
          <div data-testid="gi-bench-paired-estimate">Paired stimato: {pairedEstimate}</div>
          <div data-testid="gi-bench-pilot-paired-estimate">
            Pilot paired: {pf.pilot_paired_estimate ?? pf.availability?.pilot_paired_estimate ?? 0}
          </div>
          <div data-testid="gi-bench-five-models-probe">
            Five-model probe: {probeOk}/{probeN}
          </div>
          <div data-testid="gi-bench-data-gate">
            Data gate: {pf.pilot_data_gate_status ?? '—'}
          </div>
          <div>External API: {pf.checks?.external_api_calls ?? 0}</div>
          <div>Pilot selected: {pf.pilot?.selected ?? 0}</div>
        </div>
      ) : null}

      {pf && (pf.blocking_reasons?.length ?? 0) > 0 ? (
        <div
          className="mb-4 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-950"
          data-testid="gi-bench-blocking-reasons"
        >
          <div className="font-medium">Blocking reasons</div>
          <ul className="mt-1 list-disc pl-4">
            {(pf.blocking_reasons || []).map((r) => (
              <li key={r} className="font-mono">
                {r}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {pf && (pf.warnings?.length ?? 0) > 0 ? (
        <div
          className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950"
          data-testid="gi-bench-warnings"
        >
          <div className="font-medium">Warnings</div>
          <ul className="mt-1 list-disc pl-4">
            {(pf.warnings || []).map((w) => (
              <li key={w} className="font-mono">
                {w}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {job?.pilot_gate && job.pilot_gate.ok === false ? (
        <div
          className="mb-4 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-950"
          data-testid="gi-bench-pilot-gate-reasons"
        >
          <div className="font-medium">Pilot gate (full bloccata)</div>
          <ul className="mt-1 list-disc pl-4">
            {(job.pilot_gate.reasons || []).map((r) => (
              <li key={r} className="font-mono">
                {r}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {Object.keys(missing).length > 0 ? (
        <div className="mb-4 overflow-x-auto" data-testid="gi-bench-missing">
          <h4 className="mb-1 text-sm font-semibold">Missing reasons</h4>
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr>
                <th className="py-1 pr-3">Reason</th>
                <th className="py-1">Count</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(missing).map(([k, v]) => (
                <tr key={k}>
                  <td className="py-1 pr-3 font-mono">{k}</td>
                  <td className="py-1">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {Object.keys(modelMetrics).length > 0 ? (
        <div className="mb-4 overflow-x-auto" data-testid="gi-bench-model-table">
          <h4 className="mb-1 text-sm font-semibold">Cinque modelli (coorte paired)</h4>
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr>
                <th className="py-1 pr-3">Modello</th>
                <th className="py-1 pr-3">n</th>
                <th className="py-1 pr-3">MAE</th>
                <th className="py-1 pr-3">RMSE</th>
                <th className="py-1 pr-3">Bias</th>
                <th className="py-1">Brier O2.5</th>
              </tr>
            </thead>
            <tbody>
              {MODEL_ORDER.map((mid) => {
                const block = modelMetrics[mid] || {}
                const tg = (block.total_goals_ft || {}) as Record<string, unknown>
                const ge3 = (block.goals_ge_3 || {}) as Record<string, unknown>
                return (
                  <tr key={mid}>
                    <td className="py-1 pr-3">{MODEL_LABELS[mid] || mid}</td>
                    <td className="py-1 pr-3">{String(block.n ?? '—')}</td>
                    <td className="py-1 pr-3">{String(tg.mae ?? '—')}</td>
                    <td className="py-1 pr-3">{String(tg.rmse ?? '—')}</td>
                    <td className="py-1 pr-3">{String(tg.bias ?? '—')}</td>
                    <td className="py-1">{String(ge3.brier ?? '—')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {pairwise.length > 0 ? (
        <div className="overflow-x-auto" data-testid="gi-bench-pairwise">
          <h4 className="mb-1 text-sm font-semibold">Pairwise MAE (bootstrap 95%)</h4>
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr>
                <th className="py-1 pr-3">Left</th>
                <th className="py-1 pr-3">Right</th>
                <th className="py-1 pr-3">Delta</th>
                <th className="py-1 pr-3">CI</th>
                <th className="py-1">Preferred</th>
              </tr>
            </thead>
            <tbody>
              {pairwise.map((p, idx) => {
                const ci = (p.ci || {}) as Record<string, unknown>
                return (
                  <tr key={`${String(p.left_id)}-${String(p.right_id)}-${idx}`}>
                    <td className="py-1 pr-3 font-mono text-[10px]">{String(p.left_id)}</td>
                    <td className="py-1 pr-3 font-mono text-[10px]">{String(p.right_id)}</td>
                    <td className="py-1 pr-3">{String(p.delta ?? '—')}</td>
                    <td className="py-1 pr-3">
                      [{String(ci.ci_lower ?? '—')}, {String(ci.ci_upper ?? '—')}]
                    </td>
                    <td className="py-1">{String(p.preferred_side ?? 'none')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
