import { useCallback, useEffect, useRef, useState } from 'react'
import {
  downloadV31CalibrationDatasetCsv,
  getV31AntiLeakageReport,
  getV31CalibrationDataset,
  getV31CalibrationSummary,
  type V31CalibrationDatasetSummary,
} from '../../lib/api'

const SUMMARY_SLOW_MS = 15_000
const EXPORT_WARN_MS = 60_000

type Props = {
  competitionId: number | null
  seasonYear: number
  reloadToken: number
}

type ExportKind = 'json' | 'json-full' | 'csv' | null

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
  const exportAbortRef = useRef<AbortController | null>(null)
  const exportTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const summaryAbortRef = useRef<AbortController | null>(null)

  const clearExportTimer = useCallback(() => {
    if (exportTimerRef.current != null) {
      clearInterval(exportTimerRef.current)
      exportTimerRef.current = null
    }
    setExportSlow(false)
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

  useEffect(
    () => () => {
      stopExport()
      summaryAbortRef.current?.abort()
    },
    [stopExport],
  )

  const startExportTimer = useCallback(() => {
    clearExportTimer()
    setExportElapsed(0)
    exportTimerRef.current = setInterval(() => {
      setExportElapsed((s) => {
        const next = s + 1
        if (next >= EXPORT_WARN_MS / 1000) setExportSlow(true)
        return next
      })
    }, 1000)
  }, [clearExportTimer])

  const runExport = useCallback(
    async (kind: ExportKind) => {
      if (competitionId == null || kind == null) return
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
            detail: kind === 'json-full' ? 'full' : 'standard',
          })
          const suffix = kind === 'json-full' ? '-full' : ''
          const blob = new Blob([JSON.stringify(payload, null, 2)], {
            type: 'application/json',
          })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `v31-calibration-dataset${suffix}-${competitionId}-${seasonYear}.json`
          a.click()
          URL.revokeObjectURL(url)
        }
      } catch (e) {
        if (ac.signal.aborted) return
        setExportError(e instanceof Error ? e.message : String(e))
      } finally {
        stopExport()
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

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Dataset calibrazione v3.1</h2>
          <p className="mt-1 max-w-2xl text-xs text-slate-600">
            Feature pre-match da trace v2.1 persistito (export standard veloce). Il JSON completo
            ricostruisce PIT per ogni fixture. I confronti legacy restano in{' '}
            <code className="text-[11px]">comparisons</code>, mai in <code className="text-[11px]">features</code>.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!exportable || target === 0 || exporting}
            title={
              !exportable
                ? 'Anti-leakage failed: export disabilitato'
                : undefined
            }
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => void runExport('json')}
          >
            Scarica dataset JSON
          </button>
          <button
            type="button"
            disabled={!exportable || target === 0 || exporting}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => void runExport('csv')}
          >
            Scarica dataset CSV
          </button>
          <button
            type="button"
            disabled={!exportable || target === 0 || exporting}
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
            onClick={() => void runExport('json-full')}
          >
            Scarica JSON completo
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

      {exporting ? (
        <div className="space-y-2 rounded-lg border border-blue-200 bg-blue-50/60 p-3">
          <p className="text-sm text-blue-900">
            {exportKind === 'csv'
              ? 'Preparazione CSV…'
              : exportKind === 'json-full'
                ? 'Preparazione JSON completo (PIT)…'
                : 'Preparazione JSON…'}{' '}
            {exportElapsed > 0 ? `${exportElapsed}s` : ''}
          </p>
          {exportSlow ? (
            <p className="text-xs text-amber-800">
              Preparazione molto lunga. Possibile problema backend o dataset troppo pesante (JSON
              completo).
            </p>
          ) : null}
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
