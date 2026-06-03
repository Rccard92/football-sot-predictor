import { useCallback, useEffect, useRef, useState } from 'react'
import {
  downloadV31CalibrationDatasetCsv,
  getV31CalibrationDataset,
  getV31CalibrationSummary,
  type V31CalibrationDatasetSummary,
} from '../../lib/api'

const SUMMARY_SLOW_MS = 15_000

type Props = {
  competitionId: number | null
  seasonYear: number
  reloadToken: number
}

type ExportKind = 'json' | 'csv' | null

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
  const exportAbortRef = useRef<AbortController | null>(null)
  const exportTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const summaryAbortRef = useRef<AbortController | null>(null)

  const clearExportTimer = useCallback(() => {
    if (exportTimerRef.current != null) {
      clearInterval(exportTimerRef.current)
      exportTimerRef.current = null
    }
  }, [])

  const stopExport = useCallback(() => {
    exportAbortRef.current?.abort()
    exportAbortRef.current = null
    clearExportTimer()
    setExportKind(null)
    setExportElapsed(0)
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

  useEffect(() => () => {
    stopExport()
    summaryAbortRef.current?.abort()
  }, [stopExport])

  const startExportTimer = useCallback(() => {
    clearExportTimer()
    setExportElapsed(0)
    exportTimerRef.current = setInterval(() => {
      setExportElapsed((s) => s + 1)
    }, 1000)
  }, [clearExportTimer])

  const downloadJson = useCallback(async () => {
    if (competitionId == null) return
    stopExport()
    const ac = new AbortController()
    exportAbortRef.current = ac
    setExportKind('json')
    setExportError(null)
    startExportTimer()
    try {
      const payload = await getV31CalibrationDataset(competitionId, seasonYear, {
        signal: ac.signal,
      })
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `v31-calibration-dataset-${competitionId}-${seasonYear}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      if (ac.signal.aborted) return
      setExportError(e instanceof Error ? e.message : String(e))
    } finally {
      stopExport()
    }
  }, [competitionId, seasonYear, startExportTimer, stopExport])

  const downloadCsv = useCallback(async () => {
    if (competitionId == null) return
    stopExport()
    const ac = new AbortController()
    exportAbortRef.current = ac
    setExportKind('csv')
    setExportError(null)
    startExportTimer()
    try {
      const blob = await downloadV31CalibrationDatasetCsv(competitionId, seasonYear, {
        signal: ac.signal,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `v31-calibration-dataset-${competitionId}-${seasonYear}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      if (ac.signal.aborted) return
      setExportError(e instanceof Error ? e.message : String(e))
    } finally {
      stopExport()
    }
  }, [competitionId, seasonYear, startExportTimer, stopExport])

  if (competitionId == null) return null

  const target = summary?.fixtures_with_target ?? 0
  const total = summary?.fixtures_available ?? 0
  const feats = summary?.features
  const anti = summary?.anti_leakage_check
  const canDownload = target > 0
  const exporting = exportKind != null

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Dataset calibrazione v3.1</h2>
          <p className="mt-1 max-w-2xl text-xs text-slate-600">
            Predittore sperimentale indipendente: feature pre-match ricostruite via PIT storico al
            download. Non usa predizioni finali v1.1/v2.0/v2.1/v3.0 come input. I confronti legacy
            restano in <code className="text-[11px]">comparisons</code>, esclusi dal training.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!canDownload || exporting}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => void downloadJson()}
          >
            Scarica dataset JSON
          </button>
          <button
            type="button"
            disabled={!canDownload || exporting}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => void downloadCsv()}
          >
            Scarica dataset CSV
          </button>
        </div>
      </div>

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
                  {anti?.status ?? '—'}
                  {anti?.forbidden_fields_found?.length
                    ? ` (${anti.forbidden_fields_found.length} campi)`
                    : ''}
                </span>
              )}
            </li>
            <li>Giornate analizzate: {summary.rounds_available}</li>
            <li>Ultimo aggiornamento: {formatUpdatedAt(summary.last_updated_at)}</li>
          </ul>
        </div>
      ) : null}

      {summary && target === 0 && !loadingSummary ? (
        <p className="text-sm text-slate-500">
          Nessuna fixture idonea. Esegui analisi giornate con actual SOT e stato OK.
        </p>
      ) : null}

      {exporting ? (
        <div className="space-y-2 rounded-lg border border-blue-200 bg-blue-50/60 p-3">
          <p className="text-sm text-blue-900">
            {exportKind === 'json' ? 'Preparazione JSON…' : 'Preparazione CSV…'}{' '}
            {exportElapsed > 0 ? `${exportElapsed}s` : ''}
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-blue-100">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-500" />
          </div>
          <p className="text-xs text-blue-800">Preparazione dataset…</p>
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
