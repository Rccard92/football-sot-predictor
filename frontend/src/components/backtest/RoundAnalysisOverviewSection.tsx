import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getRoundAnalysisOverview,
  getRoundAnalysisOverviewReportCsv,
  getRoundAnalysisOverviewReportJson,
  type RoundAnalysisOverview,
} from '../../lib/api'
import { ModelRankingBar } from './ModelRankingBar'
import { ModelReliabilityScorecards } from './ModelReliabilityScorecards'

const DOWNLOAD_TOOLTIP =
  'Include tutte le giornate analizzate e i dettagli partita/modello utili alla calibrazione.'

type Props = {
  competitionId: number | null
  seasonYear: number
  reloadToken: number
  onOverviewLoaded?: (overview: RoundAnalysisOverview | null) => void
}

export function RoundAnalysisOverviewSection({
  competitionId,
  seasonYear,
  reloadToken,
  onOverviewLoaded,
}: Props) {
  const [overview, setOverview] = useState<RoundAnalysisOverview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [downloadingJson, setDownloadingJson] = useState(false)
  const [downloadingCsv, setDownloadingCsv] = useState(false)
  const onLoadedRef = useRef(onOverviewLoaded)
  onLoadedRef.current = onOverviewLoaded

  const load = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    setError(null)
    try {
      const data = await getRoundAnalysisOverview(competitionId, seasonYear)
      setOverview(data)
      onLoadedRef.current?.(data)
    } catch (e) {
      setOverview(null)
      onLoadedRef.current?.(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [competitionId, seasonYear])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  if (competitionId == null) return null

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Affidabilità modelli</h2>
          <p className="text-xs text-slate-500">
            Solo pick consigliate (Giocate) con esito · campione sulle giornate completate
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            title={DOWNLOAD_TOOLTIP}
            disabled={downloadingJson || !overview?.rounds_analyzed}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={async () => {
              if (competitionId == null) return
              setDownloadingJson(true)
              try {
                const payload = await getRoundAnalysisOverviewReportJson(
                  competitionId,
                  seasonYear,
                )
                const blob = new Blob([JSON.stringify(payload, null, 2)], {
                  type: 'application/json',
                })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `round-analysis-calibration-${competitionId}-${seasonYear}.json`
                a.click()
                URL.revokeObjectURL(url)
              } finally {
                setDownloadingJson(false)
              }
            }}
          >
            {downloadingJson ? 'Download…' : 'Scarica report aggregato JSON'}
          </button>
          <button
            type="button"
            title={DOWNLOAD_TOOLTIP}
            disabled={downloadingCsv || !overview?.rounds_analyzed}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={async () => {
              if (competitionId == null) return
              setDownloadingCsv(true)
              try {
                const blob = await getRoundAnalysisOverviewReportCsv(competitionId, seasonYear)
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `round-analysis-calibration-${competitionId}-${seasonYear}.csv`
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
      {loading ? <p className="text-sm text-slate-500">Caricamento overview…</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {overview && overview.rounds_analyzed > 0 ? (
        <>
          <ModelReliabilityScorecards models={overview.models} />
          <ModelRankingBar overview={overview} />
          <p className="text-xs text-slate-500">
            {overview.fixtures_analyzed} partite analizzate su {overview.rounds_analyzed} giornate
            ({overview.season_label})
          </p>
        </>
      ) : !loading && !error ? (
        <p className="text-sm text-slate-500">Nessuna giornata completata per questa stagione.</p>
      ) : null}
    </section>
  )
}
