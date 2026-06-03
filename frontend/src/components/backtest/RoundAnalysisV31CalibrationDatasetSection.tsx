import { useCallback, useEffect, useRef, useState } from 'react'
import {
  cancelV31FullExportJob,
  downloadV31CalibrationDatasetCsv,
  downloadV31FullExportJobJson,
  getV31AntiLeakageReport,
  getV31CalibrationDataset,
  getV31CalibrationSummary,
  getV31FullExportJob,
  startV31FullExportJob,
  type V31CalibrationDatasetSummary,
  type V31FullExportJob,
} from '../../lib/api'

const SUMMARY_SLOW_MS = 15_000
const FULL_EXPORT_WARN_MS = 60_000
const FULL_EXPORT_TIMEOUT_MS = 120_000
const FULL_JOB_POLL_MS = 2_000

type Props = {
  competitionId: number | null
  seasonYear: number
  reloadToken: number
}

type ExportKind = 'json' | 'csv' | 'json-full' | null

function formatUpdatedAt(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('it-IT')
  } catch {
    return iso
  }
}

export function RoundAnalysisV31CalibrationDatasetSection({
  competitionId,
  seasonYear,
  reloadToken,
}: Props) {
  const [summary, setSummary] = useState<V31CalibrationDatasetSummary | null>(null)
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [summarySlow, setSummarySlow] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [exportKind, setExportKind] = useState<ExportKind>(null)
  const [exportElapsed, setExportElapsed] = useState(0)
  const [exportSlow, setExportSlow] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [downloadingLeakReport, setDownloadingLeakReport] = useState(false)
  const [fullJob, setFullJob] = useState<V31FullExportJob | null>(null)
  const exportAbortRef = useRef<AbortController | null>(null)
  const exportTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fullJobIdRef = useRef<string | null>(null)
  const summaryAbortRef = useRef<AbortController | null>(null)

  const clearExportTimer = useCallback(() => {
    if (exportTimerRef.current != null) {
      clearInterval(exportTimerRef.current)
      exportTimerRef.current = null
    }
    if (pollTimerRef.current != null) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
    setExportSlow(false)
  }, [])

  const stopExport = useCallback(() => {
    exportAbortRef.current?.abort()
    exportAbortRef.current = null
    const jid = fullJobIdRef.current
    if (jid) {
      void cancelV31FullExportJob(jid).catch(() => undefined)
      fullJobIdRef.current = null
    }
    clearExportTimer()
    setExportKind(null)
    setExportElapsed(0)
    setFullJob(null)
  }, [clearExportTimer])

  const loadSummary = useCallback(async () => {
    if (competitionId == null) return
    summaryAbortRef.current?.abort()
    const ac = new AbortController()
    summaryAbortRef.current = ac
    setLoadingSummary(true)
    setSummarySlow(false)
    setError(null)
    const slowTimer = window.setTimeout(() => {
      if (!ac.signal.aborted) setSummarySlow(true)
    }, SUMMARY_SLOW_MS)
    try {
      const data = await getV31CalibrationSummary(competitionId, seasonYear, {
        signal: ac.signal,
      })
      if (!ac.signal.aborted) setSummary(data)
    } catch (e) {
      if (ac.signal.aborted) return
      setSummary(null)
      const msg = e instanceof Error ? e.message : String(e)
      setError(`Impossibile caricare la summary dataset v3.1${msg ? `: ${msg}` : ''}`)
    } finally {
      window.clearTimeout(slowTimer)
      if (!ac.signal.aborted) setLoadingSummary(false)
    }
  }, [competitionId, seasonYear])

  useEffect(() => {
    void loadSummary()
    return () => {
      summaryAbortRef.current?.abort()
    }
  }, [loadSummary, reloadToken])

  useEffect(
    () => () => {
      stopExport()
      summaryAbortRef.current?.abort()
    },
    [stopExport],
  )

  const startExportTimer = useCallback(
    (opts?: { fullJob?: boolean }) => {
      clearExportTimer()
      setExportElapsed(0)
      const warnMs = opts?.fullJob ? FULL_EXPORT_WARN_MS : 60_000
      exportTimerRef.current = setInterval(() => {
        setExportElapsed((s) => {
          const next = s + 1
          if (opts?.fullJob && next * 1000 >= warnMs) setExportSlow(true)
          return next
        })
      }, 1000)
    },
    [clearExportTimer],
  )

  const pollFullJob = useCallback(
    async (jobId: string, startedAt: number) => {
      if (fullJobIdRef.current !== jobId) return
      try {
        const status = await getV31FullExportJob(jobId)
        if (fullJobIdRef.current !== jobId) return
        setFullJob(status)

        if (status.status === 'done') {
          if (competitionId != null) {
            await downloadV31FullExportJobJson(jobId, competitionId, seasonYear)
          }
          stopExport()
          return
        }
        if (status.status === 'failed') {
          setExportError(
            status.error_message ||
              'Export completo fallito. Usa il dataset standard per la calibrazione.',
          )
          stopExport()
          return
        }
        if (status.status === 'cancelled') {
          setExportError('Export completo annullato.')
          stopExport()
          return
        }

        const elapsed = Date.now() - startedAt
        if (elapsed >= FULL_EXPORT_TIMEOUT_MS) {
          await cancelV31FullExportJob(jobId)
          setExportError(
            'Export completo interrotto per timeout. Il dataset standard è già disponibile e consigliato.',
          )
          stopExport()
          return
        }

        pollTimerRef.current = setTimeout(() => {
          void pollFullJob(jobId, startedAt)
        }, FULL_JOB_POLL_MS)
      } catch (e) {
        if (fullJobIdRef.current !== jobId) return
        setExportError(e instanceof Error ? e.message : String(e))
        stopExport()
      }
    },
    [competitionId, seasonYear, stopExport],
  )

  const startFullExport = useCallback(async () => {
    if (competitionId == null) return
    stopExport()
    setExportKind('json-full')
    setExportError(null)
    setFullJob(null)
    startExportTimer({ fullJob: true })
    const startedAt = Date.now()
    try {
      const job = await startV31FullExportJob(competitionId, seasonYear)
      fullJobIdRef.current = job.job_id
      setFullJob(job)
      pollTimerRef.current = setTimeout(() => {
        void pollFullJob(job.job_id, startedAt)
      }, FULL_JOB_POLL_MS)
    } catch (e) {
      setExportError(e instanceof Error ? e.message : String(e))
      stopExport()
    }
  }, [competitionId, seasonYear, pollFullJob, startExportTimer, stopExport])

  const runSyncExport = useCallback(
    async (kind: 'json' | 'csv') => {
      if (competitionId == null) return
      stopExport()
      const ac = new AbortController()
      exportAbortRef.current = ac
      setExportKind(kind)
      setExportError(null)
      startExportTimer()
      try {
        if (kind === 'csv') {
          const blob = await downloadV31CalibrationDatasetCsv(competitionId, seasonYear, {
            signal: ac.signal,
          })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `v31-calibration-dataset-${competitionId}-${seasonYear}.csv`
          a.click()
          URL.revokeObjectURL(url)
        } else {
          const payload = await getV31CalibrationDataset(competitionId, seasonYear, {
            signal: ac.signal,
            detail: 'standard',
          })
          const blob = new Blob([JSON.stringify(payload, null, 2)], {
            type: 'application/json',
          })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `v31-calibration-dataset-standard-${competitionId}-${seasonYear}.json`
          a.click()
          URL.revokeObjectURL(url)
        }
      } catch (e) {
        if (ac.signal.aborted) return
        setExportError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!ac.signal.aborted) stopExport()
      }
    },
    [competitionId, seasonYear, startExportTimer, stopExport],
  )

  const downloadLeakReport = useCallback(async () => {
    if (competitionId == null) return
    setDownloadingLeakReport(true)
    try {
      const report = await getV31AntiLeakageReport(competitionId, seasonYear)
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `v31-anti-leakage-report-${competitionId}-${seasonYear}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setExportError(e instanceof Error ? e.message : String(e))
    } finally {
      setDownloadingLeakReport(false)
    }
  }, [competitionId, seasonYear])

  if (competitionId == null) return null

  const target = summary?.fixtures_with_target ?? 0
  const total = summary?.fixtures_available ?? 0
  const feats = summary?.features
  const anti = summary?.anti_leakage_check
  const exportable = summary?.exportable !== false && anti?.status === 'ok'
  const exporting = exportKind != null
  const samples = anti?.sample_forbidden_fields ?? []
  const forbiddenCount =
    anti?.forbidden_fields_found_count ?? anti?.forbidden_fields_found?.length ?? 0
  const fullProgress = fullJob?.progress_pct ?? 0
  const fullRowsDone = fullJob?.rows_done ?? 0
  const fullRowsExpected = fullJob?.rows_expected ?? 0

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Dataset calibrazione v3.1</h2>
          <p className="mt-1 max-w-2xl text-xs text-slate-600">
            Per la calibrazione v3.1 usa il <strong>dataset standard</strong> (veloce, anti-leakage
            verificato). Il JSON completo è solo diagnostico e può essere molto pesante.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              disabled={!exportable || target === 0 || exporting}
              className="rounded-lg border border-slate-800 bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => void runSyncExport('json')}
            >
              Scarica dataset JSON standard
            </button>
            <button
              type="button"
              disabled={!exportable || target === 0 || exporting}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
              onClick={() => void runSyncExport('csv')}
            >
              Scarica dataset CSV
            </button>
          </div>
          <button
            type="button"
            disabled={!exportable || target === 0 || exporting}
            className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-normal text-slate-600 hover:bg-slate-100 disabled:opacity-50"
            onClick={() => void startFullExport()}
          >
            Scarica JSON completo (debug)
          </button>
          <p className="max-w-xs text-right text-[10px] text-slate-500">
            Il JSON completo può essere molto pesante. Usalo solo per debug tecnico.
          </p>
        </div>
      </div>

      {!exportable && target > 0 && !loadingSummary ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50/80 p-3 text-sm text-rose-900">
          <p className="font-medium">
            Dataset non esportabile: anti-leakage failed. Alcuni campi vietati sono presenti nelle
            feature di training.
          </p>
          <button
            type="button"
            disabled={downloadingLeakReport}
            className="mt-2 rounded border border-rose-300 bg-white px-2 py-1 text-xs font-medium hover:bg-rose-50 disabled:opacity-50"
            onClick={() => void downloadLeakReport()}
          >
            {downloadingLeakReport ? 'Download…' : 'Scarica report anti-leakage'}
          </button>
        </div>
      ) : null}

      {loadingSummary ? (
        <p className="text-sm text-slate-500">Controllo disponibilità dataset…</p>
      ) : null}
      {summarySlow && loadingSummary ? (
        <p className="text-sm text-amber-700">
          Il controllo sta richiedendo più tempo del previsto.
        </p>
      ) : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      {summary && !loadingSummary ? (
        <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50/80 p-4 text-sm text-slate-800">
          <p className="font-medium text-slate-900">Stato dataset</p>
          <ul className="space-y-1 text-xs">
            <li>Fixture disponibili: {summary.fixtures_available}</li>
            <li>
              Target SOT: {summary.fixtures_with_target}/{summary.fixtures_available}
            </li>
            <li>
              Player layer: {feats?.player_layer_available ?? 0}/{target || total}
            </li>
            <li>
              Lineups: {feats?.lineups_available ?? 0}/{target || total}
            </li>
            <li>
              Indisponibili: {feats?.unavailable_available ?? 0}/{target || total}
            </li>
            <li>
              Team stats (proxy v2.1): {feats?.team_stats_available ?? 0}/{target || total}
            </li>
            <li>
              Macro features: {feats?.macro_features_available ?? 0}/{target || total}
            </li>
            <li>
              Anti-leakage:{' '}
              {anti?.status === 'ok' ? (
                <span className="font-medium text-emerald-700">OK</span>
              ) : (
                <span className="font-medium text-rose-700">
                  failed ({forbiddenCount} campi)
                </span>
              )}
            </li>
            <li>Giornate analizzate: {summary.rounds_available}</li>
            <li>Ultimo aggiornamento: {formatUpdatedAt(summary.last_updated_at)}</li>
          </ul>
          {anti?.status !== 'ok' && samples.length > 0 ? (
            <div className="mt-2 border-t border-slate-200 pt-2 text-xs">
              <p className="font-medium text-slate-700">Esempi campi vietati (max 20):</p>
              <ul className="mt-1 max-h-32 overflow-y-auto font-mono text-[10px] text-slate-600">
                {samples.map((s, i) => (
                  <li key={`${s.fixture_id}-${s.path}-${i}`}>
                    fixture {s.fixture_id}: {s.path} → {s.field}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {summary && target === 0 && !loadingSummary ? (
        <p className="text-sm text-slate-500">
          Nessuna fixture idonea. Esegui analisi giornate con actual SOT e stato OK.
        </p>
      ) : null}

      {exporting && exportKind === 'json-full' ? (
        <div className="space-y-2 rounded-lg border border-blue-200 bg-blue-50/60 p-3">
          <p className="text-sm text-blue-900">
            Preparazione JSON completo… {exportElapsed > 0 ? `${exportElapsed}s` : ''}
            {fullRowsExpected > 0
              ? ` — ${fullRowsDone}/${fullRowsExpected} fixture`
              : null}
            {fullJob?.current_fixture_id != null
              ? ` (fixture ${fullJob.current_fixture_id})`
              : null}
          </p>
          {exportSlow ? (
            <p className="text-xs text-amber-800">
              Export completo troppo pesante. Usa il dataset standard oppure attendi il job
              asincrono in background.
            </p>
          ) : null}
          {fullRowsExpected > 0 ? (
            <div className="h-2 w-full overflow-hidden rounded-full bg-blue-100">
              <div
                className="h-full rounded-full bg-blue-600 transition-all duration-300"
                style={{ width: `${Math.min(100, Math.max(0, fullProgress))}%` }}
              />
            </div>
          ) : (
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-blue-100">
              <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-500" />
            </div>
          )}
          <p className="text-xs text-blue-800">
            Job asincrono: {fullJob?.status ?? 'avvio…'}
            {fullProgress > 0 ? ` (${fullProgress.toFixed(0)}%)` : ''}
          </p>
          <button
            type="button"
            className="rounded border border-blue-300 bg-white px-2 py-1 text-xs font-medium text-blue-900 hover:bg-blue-50"
            onClick={() => stopExport()}
          >
            Annulla preparazione
          </button>
        </div>
      ) : null}

      {exporting && exportKind !== 'json-full' ? (
        <div className="space-y-2 rounded-lg border border-blue-200 bg-blue-50/60 p-3">
          <p className="text-sm text-blue-900">
            {exportKind === 'csv' ? 'Preparazione CSV…' : 'Preparazione JSON standard…'}{' '}
            {exportElapsed > 0 ? `${exportElapsed}s` : ''}
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-blue-100">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-500" />
          </div>
          <button
            type="button"
            className="rounded border border-blue-300 bg-white px-2 py-1 text-xs font-medium text-blue-900 hover:bg-blue-50"
            onClick={() => stopExport()}
          >
            Annulla preparazione
          </button>
        </div>
      ) : null}

      {exportError ? <p className="text-sm text-rose-700">{exportError}</p> : null}
    </section>
  )
}
