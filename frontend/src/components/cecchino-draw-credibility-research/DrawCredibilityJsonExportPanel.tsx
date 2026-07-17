import { useMemo, useState } from 'react'
import type { DrawCredibilityStatisticsResponse } from '../../lib/cecchinoDrawCredibilityResearchApi'
import {
  STATISTICS_EXPORT_SECTIONS,
  buildStatisticsFullFilename,
  buildStatisticsSectionExport,
  buildStatisticsSectionFilename,
  downloadJsonFile,
  estimateJsonByteSize,
  formatApproxJsonSize,
  type StatisticsExportSectionKey,
} from '../../lib/downloadJsonFile'

type Props = {
  analysis: DrawCredibilityStatisticsResponse | null
  lastExecutedAt: string | null
}

export function DrawCredibilityJsonExportPanel({ analysis, lastExecutedAt }: Props) {
  const [section, setSection] = useState<StatisticsExportSectionKey>('dataset_summary')
  const [exportError, setExportError] = useState<string | null>(null)

  const hasAnalysis = analysis != null
  const approxSize = useMemo(() => {
    if (!analysis) return '—'
    try {
      return formatApproxJsonSize(estimateJsonByteSize(analysis))
    } catch {
      return '—'
    }
  }, [analysis])

  const onDownloadFull = () => {
    if (!analysis) return
    setExportError(null)
    try {
      const filename = buildStatisticsFullFilename(
        analysis.version,
        analysis.filters.date_from,
        analysis.filters.date_to,
      )
      downloadJsonFile(filename, analysis)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err))
    }
  }

  const onDownloadSection = () => {
    if (!analysis) return
    setExportError(null)
    try {
      const payload = buildStatisticsSectionExport(analysis, section)
      const filename = buildStatisticsSectionFilename(
        section,
        analysis.filters.date_from,
        analysis.filters.date_to,
      )
      downloadJsonFile(filename, payload)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-1 text-sm font-semibold text-slate-800">Export JSON</h3>
      <p className="mb-3 text-xs text-slate-600">
        Il JSON contiene il payload tecnico completo dell&apos;analisi e non modifica il modello
        produttivo.
      </p>

      <div className="mb-4 grid gap-2 text-xs text-slate-700 sm:grid-cols-2 lg:grid-cols-3">
        <p>
          <span className="font-medium text-slate-500">Versione:</span>{' '}
          {analysis?.version ?? '—'}
        </p>
        <p>
          <span className="font-medium text-slate-500">Periodo:</span>{' '}
          {analysis
            ? `${analysis.filters.date_from} → ${analysis.filters.date_to}`
            : '—'}
        </p>
        <p>
          <span className="font-medium text-slate-500">Primary rows:</span>{' '}
          {analysis?.dataset_summary.primary.rows ?? '—'}
        </p>
        <p>
          <span className="font-medium text-slate-500">Ultima esecuzione:</span>{' '}
          {lastExecutedAt ? new Date(lastExecutedAt).toLocaleString('it-IT') : '—'}
        </p>
        <p>
          <span className="font-medium text-slate-500">Dimensione JSON:</span> {approxSize}
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <button
          type="button"
          disabled={!hasAnalysis}
          className="rounded-lg bg-violet-600 px-3 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
          onClick={onDownloadFull}
        >
          Scarica JSON completo
        </button>

        <label className="block text-xs text-slate-600">
          Sezione
          <select
            className="mt-1 block min-w-[14rem] rounded-lg border border-slate-200 px-2 py-1.5 text-sm disabled:opacity-50"
            value={section}
            disabled={!hasAnalysis}
            onChange={(e) => setSection(e.target.value as StatisticsExportSectionKey)}
          >
            {STATISTICS_EXPORT_SECTIONS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          disabled={!hasAnalysis}
          className="rounded-lg border border-violet-300 bg-violet-50 px-3 py-2 text-sm font-medium text-violet-900 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-50"
          onClick={onDownloadSection}
        >
          Scarica sezione JSON
        </button>
      </div>

      {exportError ? (
        <p className="mt-3 text-xs text-red-700" role="alert">
          {exportError}
        </p>
      ) : null}
    </section>
  )
}
