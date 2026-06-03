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
const FULL_EXPORT_STALL_MS = 90_000
const FULL_JOB_POLL_MS = 2_000
const CHUNK_TOTAL_PARTS = 3

const V31_FULL_EXPORT_CHUNKS = [
  { part: 1, roundFrom: 5, roundTo: 15 },
  { part: 2, roundFrom: 16, roundTo: 26 },
  { part: 3, roundFrom: 27, roundTo: 37 },
] as const

type Props = {
  competitionId: number | null
  seasonYear: number
  reloadToken: number
}

type ExportKind = 'json' | 'csv' | null
type ChunkUiStatus = 'idle' | 'running' | 'ready' | 'error' | 'cancelled'

type ChunkState = {
  status: ChunkUiStatus
  job: V31FullExportJob | null
  jobId: string | null
  error: string | null
  elapsed: number
  slowWarn: boolean
  stallWarn: boolean
  lastRowsDone: number | null
  lastProgressAt: number | null
}

function initialChunkState(): ChunkState {
  return {
    status: 'idle',
    job: null,
    jobId: null,
    error: null,
    elapsed: 0,
    slowWarn: false,
    stallWarn: false,
    lastRowsDone: null,
    lastProgressAt: null,
  }
}

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
  const [exportError, setExportError] = useState<string | null>(null)
  const [downloadingLeakReport, setDownloadingLeakReport] = useState(false)
  const [chunks, setChunks] = useState<Record<number, ChunkState>>(() =>
    Object.fromEntries(V31_FULL_EXPORT_CHUNKS.map((c) => [c.part, initialChunkState()])),
  )

  const exportAbortRef = useRef<AbortController | null>(null)
  const exportTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const chunkPollRefs = useRef<Record<number, ReturnType<typeof setTimeout> | null>>({})
  const chunkTimerRefs = useRef<Record<number, ReturnType<typeof setInterval> | null>>({})
  const chunkJobIdRefs = useRef<Record<number, string | null>>({})
  const summaryAbortRef = useRef<AbortController | null>(null)

  const clearSyncExportTimer = useCallback(() => {
    if (exportTimerRef.current != null) {
      clearInterval(exportTimerRef.current)
      exportTimerRef.current = null
    }
  }, [])

  const stopSyncExport = useCallback(() => {
    exportAbortRef.current?.abort()
    exportAbortRef.current = null
    clearSyncExportTimer()
    setExportKind(null)
    setExportElapsed(0)
  }, [clearSyncExportTimer])

  const clearChunkTimers = useCallback((part: number) => {
    const poll = chunkPollRefs.current[part]
    if (poll != null) {
      clearTimeout(poll)
      chunkPollRefs.current[part] = null
    }
    const timer = chunkTimerRefs.current[part]
    if (timer != null) {
      clearInterval(timer)
      chunkTimerRefs.current[part] = null
    }
  }, [])

  const updateChunk = useCallback((part: number, patch: Partial<ChunkState>) => {
    setChunks((prev) => ({
      ...prev,
      [part]: { ...prev[part], ...patch },
    }))
  }, [])

  const stopChunk = useCallback(
    (part: number, finalStatus?: ChunkUiStatus) => {
      const jid = chunkJobIdRefs.current[part]
      if (jid) {
        void cancelV31FullExportJob(jid).catch(() => undefined)
        chunkJobIdRefs.current[part] = null
      }
      clearChunkTimers(part)
      setChunks((prev) => ({
        ...prev,
        [part]: {
          ...prev[part],
          status: finalStatus ?? prev[part].status,
          jobId: null,
        },
      }))
    },
    [clearChunkTimers],
  )

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
      stopSyncExport()
      summaryAbortRef.current?.abort()
      for (const c of V31_FULL_EXPORT_CHUNKS) {
        stopChunk(c.part, 'idle')
      }
    },
    [stopSyncExport, stopChunk],
  )

  const startChunkElapsedTimer = useCallback(
    (part: number) => {
      clearChunkTimers(part)
      updateChunk(part, { elapsed: 0, slowWarn: false, stallWarn: false })
      chunkTimerRefs.current[part] = setInterval(() => {
        setChunks((prev) => {
          const ch = prev[part]
          const nextElapsed = ch.elapsed + 1
          const slowWarn = ch.slowWarn || nextElapsed * 1000 >= FULL_EXPORT_WARN_MS
          let stallWarn = ch.stallWarn
          if (
            ch.lastProgressAt != null &&
            ch.status === 'running' &&
            Date.now() - ch.lastProgressAt >= FULL_EXPORT_STALL_MS
          ) {
            stallWarn = true
          }
          return {
            ...prev,
            [part]: { ...ch, elapsed: nextElapsed, slowWarn, stallWarn },
          }
        })
      }, 1000)
    },
    [clearChunkTimers, updateChunk],
  )

  const pollChunkJob = useCallback(
    async (
      part: number,
      jobId: string,
      roundFrom: number,
      roundTo: number,
    ) => {
      if (chunkJobIdRefs.current[part] !== jobId) return
      try {
        const status = await getV31FullExportJob(jobId)
        if (chunkJobIdRefs.current[part] !== jobId) return

        setChunks((prev) => {
          const ch = prev[part]
          const rowsDone = status.rows_done ?? 0
          const progressed =
            ch.lastRowsDone == null || rowsDone > ch.lastRowsDone
          return {
            ...prev,
            [part]: {
              ...ch,
              job: status,
              lastRowsDone: rowsDone,
              lastProgressAt: progressed ? Date.now() : ch.lastProgressAt,
              stallWarn:
                ch.lastProgressAt != null &&
                !progressed &&
                ch.status === 'running' &&
                Date.now() - ch.lastProgressAt >= FULL_EXPORT_STALL_MS,
            },
          }
        })

        if (status.status === 'done') {
          chunkJobIdRefs.current[part] = null
          clearChunkTimers(part)
          updateChunk(part, { status: 'ready', job: status, jobId: null })
          return
        }
        if (status.status === 'failed') {
          clearChunkTimers(part)
          chunkJobIdRefs.current[part] = null
          updateChunk(part, {
            status: 'error',
            job: status,
            jobId: null,
            error:
              status.error_message ||
              'Export chunk fallito. Usa il dataset standard per la calibrazione.',
          })
          return
        }
        if (status.status === 'cancelled') {
          clearChunkTimers(part)
          chunkJobIdRefs.current[part] = null
          updateChunk(part, {
            status: 'cancelled',
            job: status,
            jobId: null,
            error: 'Export annullato.',
          })
          return
        }

        chunkPollRefs.current[part] = setTimeout(() => {
          void pollChunkJob(part, jobId, roundFrom, roundTo)
        }, FULL_JOB_POLL_MS)
      } catch (e) {
        if (chunkJobIdRefs.current[part] !== jobId) return
        clearChunkTimers(part)
        chunkJobIdRefs.current[part] = null
        updateChunk(part, {
          status: 'error',
          jobId: null,
          error: e instanceof Error ? e.message : String(e),
        })
      }
    },
    [clearChunkTimers, updateChunk],
  )

  const startChunkExport = useCallback(
    async (part: number, roundFrom: number, roundTo: number) => {
      if (competitionId == null) return
      stopChunk(part, 'idle')
      updateChunk(part, {
        status: 'running',
        job: null,
        jobId: null,
        error: null,
        lastRowsDone: null,
        lastProgressAt: Date.now(),
        stallWarn: false,
        slowWarn: false,
      })
      startChunkElapsedTimer(part)
      try {
        const job = await startV31FullExportJob(competitionId, seasonYear, {
          roundFrom,
          roundTo,
          chunkPart: part,
          chunkTotalParts: CHUNK_TOTAL_PARTS,
        })
        chunkJobIdRefs.current[part] = job.job_id
        updateChunk(part, { job, jobId: job.job_id })
        chunkPollRefs.current[part] = setTimeout(() => {
          void pollChunkJob(part, job.job_id, roundFrom, roundTo)
        }, FULL_JOB_POLL_MS)
      } catch (e) {
        clearChunkTimers(part)
        updateChunk(part, {
          status: 'error',
          error: e instanceof Error ? e.message : String(e),
        })
      }
    },
    [
      competitionId,
      seasonYear,
      pollChunkJob,
      startChunkElapsedTimer,
      stopChunk,
      updateChunk,
    ],
  )

  const downloadChunk = useCallback(
    async (part: number, roundFrom: number, roundTo: number) => {
      if (competitionId == null) return
      const ch = chunks[part]
      const jobId = ch.job?.job_id ?? ch.jobId
      if (!jobId) return
      try {
        await downloadV31FullExportJobJson(jobId, {
          competitionId,
          seasonYear,
          chunkPart: part,
          roundFrom,
          roundTo,
        })
      } catch (e) {
        updateChunk(part, {
          error: e instanceof Error ? e.message : String(e),
        })
      }
    },
    [chunks, competitionId, seasonYear, updateChunk],
  )

  const cancelChunk = useCallback(
    (part: number) => {
      stopChunk(part, 'cancelled')
      updateChunk(part, { error: 'Export annullato.' })
    },
    [stopChunk, updateChunk],
  )

  const regenerateChunk = useCallback(
    (part: number, roundFrom: number, roundTo: number) => {
      updateChunk(part, initialChunkState())
      void startChunkExport(part, roundFrom, roundTo)
    },
    [startChunkExport, updateChunk],
  )

  const startSyncExportTimer = useCallback(() => {
    clearSyncExportTimer()
    setExportElapsed(0)
    exportTimerRef.current = setInterval(() => {
      setExportElapsed((s) => s + 1)
    }, 1000)
  }, [clearSyncExportTimer])

  const runSyncExport = useCallback(
    async (kind: 'json' | 'csv') => {
      if (competitionId == null) return
      stopSyncExport()
      const ac = new AbortController()
      exportAbortRef.current = ac
      setExportKind(kind)
      setExportError(null)
      startSyncExportTimer()
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
        if (!ac.signal.aborted) stopSyncExport()
      }
    },
    [competitionId, seasonYear, startSyncExportTimer, stopSyncExport],
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
  const exportingSync = exportKind != null
  const samples = anti?.sample_forbidden_fields ?? []
  const forbiddenCount =
    anti?.forbidden_fields_found_count ?? anti?.forbidden_fields_found?.length ?? 0
  const anyChunkRunning = V31_FULL_EXPORT_CHUNKS.some(
    (c) => chunks[c.part]?.status === 'running',
  )

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Dataset calibrazione v3.1</h2>
          <p className="mt-1 max-w-2xl text-xs text-slate-600">
            Per la calibrazione v3.1 usa il <strong>dataset standard</strong> (veloce, anti-leakage
            verificato). Il JSON completo è solo diagnostico e viene diviso in 3 file.
          </p>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            disabled={!exportable || target === 0 || exportingSync || anyChunkRunning}
            className="rounded-lg border border-slate-800 bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            onClick={() => void runSyncExport('json')}
          >
            Scarica dataset JSON standard
          </button>
          <button
            type="button"
            disabled={!exportable || target === 0 || exportingSync || anyChunkRunning}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => void runSyncExport('csv')}
          >
            Scarica dataset CSV
          </button>
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

      {exportable && target > 0 ? (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <div>
            <p className="text-sm font-medium text-slate-900">JSON completo (debug) — 3 parti</p>
            <p className="mt-1 text-xs text-slate-600">
              Il JSON completo viene diviso in 3 file perché ricostruisce il contesto PIT completo
              per ogni fixture (~3–4 min per parte).
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-1 lg:grid-cols-3">
            {V31_FULL_EXPORT_CHUNKS.map(({ part, roundFrom, roundTo }) => {
              const ch = chunks[part] ?? initialChunkState()
              const job = ch.job
              const progress = job?.progress_pct ?? 0
              const rowsDone = job?.rows_done ?? 0
              const rowsExpected = job?.rows_expected ?? 0
              const isRunning = ch.status === 'running'
              const isReady = ch.status === 'ready'
              const busy = isRunning || exportingSync

              return (
                <div
                  key={part}
                  className="space-y-2 rounded-lg border border-slate-200 bg-slate-50/60 p-3"
                >
                  <p className="text-xs font-semibold text-slate-800">
                    Parte {part}/{CHUNK_TOTAL_PARTS} — giornate {roundFrom}–{roundTo}
                  </p>
                  <p className="text-[10px] text-slate-500 capitalize">Stato: {ch.status}</p>

                  {isRunning ? (
                    <div className="space-y-1">
                      <p className="text-xs text-blue-900">
                        {ch.elapsed > 0 ? `${ch.elapsed}s` : 'Avvio…'}
                        {rowsExpected > 0
                          ? ` — ${rowsDone}/${rowsExpected} fixture`
                          : null}
                        {job?.current_fixture_id != null
                          ? ` (fixture ${job.current_fixture_id})`
                          : null}
                      </p>
                      {ch.slowWarn ? (
                        <p className="text-[10px] text-amber-800">
                          Export pesante in corso; il dataset standard resta consigliato.
                        </p>
                      ) : null}
                      {ch.stallWarn ? (
                        <p className="text-[10px] text-amber-900 font-medium">
                          Il job non sta avanzando da 90s. Attendi o annulla manualmente.
                        </p>
                      ) : null}
                      {rowsExpected > 0 ? (
                        <div className="h-2 w-full overflow-hidden rounded-full bg-blue-100">
                          <div
                            className="h-full rounded-full bg-blue-600 transition-all duration-300"
                            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
                          />
                        </div>
                      ) : (
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-blue-100">
                          <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-500" />
                        </div>
                      )}
                      <p className="text-[10px] text-blue-800">
                        {job?.status ?? 'queued'}
                        {progress > 0 ? ` (${progress.toFixed(0)}%)` : ''}
                      </p>
                    </div>
                  ) : null}

                  {ch.error ? (
                    <p className="text-[10px] text-rose-700">{ch.error}</p>
                  ) : null}

                  <div className="flex flex-wrap gap-1.5">
                    {!isRunning && !isReady ? (
                      <button
                        type="button"
                        disabled={busy}
                        className="rounded border border-slate-700 bg-slate-700 px-2 py-1 text-[10px] font-medium text-white hover:bg-slate-600 disabled:opacity-50"
                        onClick={() => void startChunkExport(part, roundFrom, roundTo)}
                      >
                        Genera
                      </button>
                    ) : null}
                    {isReady ? (
                      <>
                        <button
                          type="button"
                          className="rounded border border-emerald-600 bg-emerald-600 px-2 py-1 text-[10px] font-medium text-white hover:bg-emerald-500"
                          onClick={() => void downloadChunk(part, roundFrom, roundTo)}
                        >
                          Scarica
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded border border-slate-300 bg-white px-2 py-1 text-[10px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                          onClick={() => regenerateChunk(part, roundFrom, roundTo)}
                        >
                          Rigenera
                        </button>
                      </>
                    ) : null}
                    {isRunning ? (
                      <button
                        type="button"
                        className="rounded border border-rose-300 bg-white px-2 py-1 text-[10px] font-medium text-rose-800 hover:bg-rose-50"
                        onClick={() => cancelChunk(part)}
                      >
                        Annulla
                      </button>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}

      {exportingSync ? (
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
            onClick={() => stopSyncExport()}
          >
            Annulla preparazione
          </button>
        </div>
      ) : null}

      {exportError ? <p className="text-sm text-rose-700">{exportError}</p> : null}
    </section>
  )
}
