import { useCallback, useEffect, useState } from 'react'
import {
  downloadV31CalibrationDatasetCsv,
  getV31CalibrationDataset,
  type V31CalibrationDataset,
} from '../../lib/api'

type Props = {
  competitionId: number | null
  seasonYear: number
  reloadToken: number
}

export function RoundAnalysisV31CalibrationDatasetSection({
  competitionId,
  seasonYear,
  reloadToken,
}: Props) {
  const [dataset, setDataset] = useState<V31CalibrationDataset | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [downloadingJson, setDownloadingJson] = useState(false)
  const [downloadingCsv, setDownloadingCsv] = useState(false)

  const load = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    setError(null)
    try {
      const data = await getV31CalibrationDataset(competitionId, seasonYear)
      setDataset(data)
    } catch (e) {
      setDataset(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [competitionId, seasonYear])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  if (competitionId == null) return null

  const cov = dataset?.coverage_summary
  const anti = dataset?.anti_leakage_check

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Dataset calibrazione v3.1</h2>
          <p className="mt-1 max-w-2xl text-xs text-slate-600">
            Predittore sperimentale indipendente: feature pre-match ricostruite via PIT storico.
            Non usa predizioni finali v1.1/v2.0/v2.1/v3.0 come input. I confronti con i modelli
            legacy restano in <code className="text-[11px]">comparisons</code>, esclusi dal training.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={downloadingJson || !dataset?.fixtures_count}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={async () => {
              if (competitionId == null) return
              setDownloadingJson(true)
              try {
                const payload = await getV31CalibrationDataset(competitionId, seasonYear)
                const blob = new Blob([JSON.stringify(payload, null, 2)], {
                  type: 'application/json',
                })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `v31-calibration-dataset-${competitionId}-${seasonYear}.json`
                a.click()
                URL.revokeObjectURL(url)
              } finally {
                setDownloadingJson(false)
              }
            }}
          >
            {downloadingJson ? 'Download…' : 'Scarica dataset JSON'}
          </button>
          <button
            type="button"
            disabled={downloadingCsv || !dataset?.fixtures_count}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={async () => {
              if (competitionId == null) return
              setDownloadingCsv(true)
              try {
                const blob = await downloadV31CalibrationDatasetCsv(competitionId, seasonYear)
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `v31-calibration-dataset-${competitionId}-${seasonYear}.csv`
                a.click()
                URL.revokeObjectURL(url)
              } finally {
                setDownloadingCsv(false)
              }
            }}
          >
            {downloadingCsv ? 'Download…' : 'Scarica dataset CSV'}
          </button>
        </div>
      </div>

      {loading ? <p className="text-sm text-slate-500">Caricamento dataset v3.1…</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      {dataset && dataset.fixtures_count > 0 ? (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-800">
            {dataset.fixtures_count} fixture
          </span>
          {cov ? (
            <>
              <span className="rounded-full bg-blue-100 px-2 py-1 text-blue-800">
                Player layer {cov.player_layer_available_pct}%
              </span>
              <span className="rounded-full bg-indigo-100 px-2 py-1 text-indigo-800">
                Lineups {cov.lineups_available_pct}%
              </span>
              <span className="rounded-full bg-violet-100 px-2 py-1 text-violet-800">
                Unavailable {cov.unavailable_available_pct}%
              </span>
            </>
          ) : null}
          {anti?.status === 'ok' ? (
            <span className="rounded-full bg-emerald-100 px-2 py-1 text-emerald-800">
              Anti-leakage OK
            </span>
          ) : (
            <span className="rounded-full bg-rose-100 px-2 py-1 text-rose-800">
              Anti-leakage: {anti?.status ?? '—'}
            </span>
          )}
          {dataset.comparisons_are_not_features ? (
            <span className="rounded-full bg-amber-50 px-2 py-1 text-amber-900">
              Comparisons ≠ features
            </span>
          ) : null}
        </div>
      ) : dataset && dataset.fixtures_count === 0 ? (
        <p className="text-sm text-slate-500">
          Nessuna fixture idonea. Esegui analisi giornate con actual SOT e stato OK.
        </p>
      ) : null}

      {cov?.top_warnings?.length ? (
        <p className="text-xs text-slate-500">
          Warning frequenti:{' '}
          {cov.top_warnings.map((w) => `${w.code} (${w.count})`).join(', ')}
        </p>
      ) : null}
    </section>
  )
}
