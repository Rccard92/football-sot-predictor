import { useState } from 'react'
import type {
  DrawCredibilityModelComparisonResponse,
  DrawCredibilityOofPrediction,
} from '../../lib/cecchinoDrawCredibilityResearchApi'
import {
  buildModelComparisonFullFilename,
  buildModelComparisonOofCsvFilename,
  downloadCsvFile,
  downloadJsonFile,
} from '../../lib/downloadJsonFile'

type Props = {
  analysis: DrawCredibilityModelComparisonResponse | null
  lastExecutedAt: string | null
}

const OOF_HEADERS = [
  'provider_fixture_id',
  'kickoff',
  'draw_ft',
  'model_key',
  'fold_id',
  'predicted_draw_probability',
  'predicted_credibility_0_100',
  'is_market_row',
  'quota_book_x',
  'prob_book_x_norm',
]

function oofRows(preds: DrawCredibilityOofPrediction[]): Array<Array<unknown>> {
  return preds.map((r) => [
    r.provider_fixture_id,
    r.kickoff,
    r.draw_ft,
    r.model_key,
    r.fold_id,
    r.predicted_draw_probability,
    r.predicted_credibility_0_100,
    r.is_market_row ? 1 : 0,
    r.quota_book_x ?? '',
    r.prob_book_x_norm ?? '',
  ])
}

export function DrawCredibilityModelComparisonExportPanel({ analysis, lastExecutedAt }: Props) {
  const [exportError, setExportError] = useState<string | null>(null)
  const has = analysis != null
  const filters = (analysis?.filters ?? {}) as { date_from?: string; date_to?: string }

  const onJson = () => {
    if (!analysis) return
    setExportError(null)
    try {
      downloadJsonFile(
        buildModelComparisonFullFilename(String(filters.date_from ?? ''), String(filters.date_to ?? '')),
        analysis,
      )
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err))
    }
  }

  const onCsv = () => {
    if (!analysis?.oof_predictions?.length) {
      setExportError('Nessuna prediction OOF disponibile')
      return
    }
    setExportError(null)
    try {
      downloadCsvFile(
        buildModelComparisonOofCsvFilename(String(filters.date_from ?? ''), String(filters.date_to ?? '')),
        OOF_HEADERS,
        oofRows(analysis.oof_predictions),
      )
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-1 text-sm font-semibold text-slate-800">Export confronto modelli</h3>
      <p className="mb-3 text-xs text-slate-600">
        JSON = payload tecnico completo non trasformato. CSV = sole prediction OOF (colonne stabili).
      </p>
      <div className="mb-3 grid gap-2 text-xs text-slate-700 sm:grid-cols-3">
        <p>
          <span className="font-medium text-slate-500">Versione:</span> {analysis?.version ?? '—'}
        </p>
        <p>
          <span className="font-medium text-slate-500">OOF rows:</span>{' '}
          {analysis?.oof_predictions?.length ?? '—'}
        </p>
        <p>
          <span className="font-medium text-slate-500">Ultima esecuzione:</span>{' '}
          {lastExecutedAt ? new Date(lastExecutedAt).toLocaleString('it-IT') : '—'}
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={!has}
          className="rounded-lg bg-violet-600 px-3 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
          onClick={onJson}
        >
          Scarica JSON confronto modelli
        </button>
        <button
          type="button"
          disabled={!has || !analysis?.oof_predictions?.length}
          className="rounded-lg border border-violet-300 bg-violet-50 px-3 py-2 text-sm font-medium text-violet-900 disabled:opacity-50"
          onClick={onCsv}
        >
          Scarica CSV prediction OOF
        </button>
      </div>
      {exportError ? (
        <p className="mt-2 text-xs text-red-700" role="alert">
          {exportError}
        </p>
      ) : null}
    </section>
  )
}
