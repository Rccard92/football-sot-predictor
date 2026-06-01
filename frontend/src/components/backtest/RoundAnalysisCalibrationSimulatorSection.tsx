import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getRoundAnalysisCalibrationSimulator,
  getRoundAnalysisCalibrationSimulatorReportJson,
  type CalibrationSimulatorStrategyBlock,
  type RoundAnalysisCalibrationSimulator,
} from '../../lib/api'

type Props = {
  competitionId: number | null
  seasonYear: number
  reloadToken: number
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v.toFixed(1)}%`
}

function fmtDelta(v: number | null | undefined): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}`
}

function strategyLabel(id: string, block: CalibrationSimulatorStrategyBlock): string {
  return block.label || id
}

export function RoundAnalysisCalibrationSimulatorSection({
  competitionId,
  seasonYear,
  reloadToken,
}: Props) {
  const [simulator, setSimulator] = useState<RoundAnalysisCalibrationSimulator | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null)
  const [downloadingJson, setDownloadingJson] = useState(false)

  const load = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    setError(null)
    try {
      const data = await getRoundAnalysisCalibrationSimulator(competitionId, seasonYear)
      setSimulator(data)
      const first = Object.keys(data.strategies)[0]
      setSelectedStrategy(data.ranking.best_hit_rate ?? first ?? null)
    } catch (e) {
      setSimulator(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [competitionId, seasonYear])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  const strategyRows = useMemo(() => {
    if (!simulator) return []
    return Object.entries(simulator.strategies).map(([id, block]) => ({ id, block }))
  }, [simulator])

  const selected = selectedStrategy && simulator?.strategies[selectedStrategy]

  if (competitionId == null) return null

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Simulatore calibrazione v3.0</h2>
          <p className="text-xs text-slate-500">
            Simulazione read-only di strategie di selezione pick — nessun ricalcolo predizioni
          </p>
        </div>
        <button
          type="button"
          disabled={downloadingJson || !simulator?.metadata.analyzed_fixtures}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          onClick={async () => {
            if (competitionId == null) return
            setDownloadingJson(true)
            try {
              const payload = await getRoundAnalysisCalibrationSimulatorReportJson(
                competitionId,
                seasonYear,
              )
              const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `round-analysis-calibration-simulator-${competitionId}-${seasonYear}.json`
              a.click()
              URL.revokeObjectURL(url)
            } finally {
              setDownloadingJson(false)
            }
          }}
        >
          {downloadingJson ? 'Download…' : 'Scarica simulazione calibrazione JSON'}
        </button>
      </div>

      {loading ? <p className="text-sm text-slate-500">Caricamento simulatore…</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      {simulator && simulator.metadata.analyzed_fixtures > 0 ? (
        <>
          <div className="flex flex-wrap gap-2 text-xs">
            {simulator.ranking.best_hit_rate ? (
              <span className="rounded-full bg-emerald-100 px-2 py-1 text-emerald-800">
                Miglior hit rate: {strategyLabel(simulator.ranking.best_hit_rate, simulator.strategies[simulator.ranking.best_hit_rate])}
              </span>
            ) : null}
            {simulator.ranking.best_volume ? (
              <span className="rounded-full bg-blue-100 px-2 py-1 text-blue-800">
                Maggior volume: {strategyLabel(simulator.ranking.best_volume, simulator.strategies[simulator.ranking.best_volume])}
              </span>
            ) : null}
            {simulator.ranking.most_balanced ? (
              <span className="rounded-full bg-violet-100 px-2 py-1 text-violet-800">
                Più equilibrata: {strategyLabel(simulator.ranking.most_balanced, simulator.strategies[simulator.ranking.most_balanced])}
              </span>
            ) : null}
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-600">
                  <th className="px-2 py-2">Strategia</th>
                  <th className="px-2 py-2">Pick</th>
                  <th className="px-2 py-2">Hit rate</th>
                  <th className="px-2 py-2">Δ vs v1.1</th>
                  <th className="px-2 py-2">Δ vs v2.1</th>
                  <th className="px-2 py-2">Evitate perdite</th>
                </tr>
              </thead>
              <tbody>
                {strategyRows.map(({ id, block }) => (
                  <tr
                    key={id}
                    className={`cursor-pointer border-b border-slate-100 ${selectedStrategy === id ? 'bg-slate-50' : ''}`}
                    onClick={() => setSelectedStrategy(id)}
                  >
                    <td className="px-2 py-2 font-medium">{block.label}</td>
                    <td className="px-2 py-2">{block.summary.picks}</td>
                    <td className="px-2 py-2">{fmtPct(block.summary.hit_rate)}</td>
                    <td className="px-2 py-2">{fmtDelta(block.vs_v1_1_baseline.delta_hit_rate)}</td>
                    <td className="px-2 py-2">{fmtDelta(block.vs_v2_1_baseline.delta_hit_rate)}</td>
                    <td className="px-2 py-2">{block.vs_v2_1_baseline.avoided_losses}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selected ? (
            <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
              <h3 className="text-sm font-semibold text-slate-900">Dettaglio: {selected.label}</h3>
              <p className="text-xs text-slate-600">
                MAE {selected.summary.mae?.toFixed(2) ?? '—'} · Bias {selected.summary.bias?.toFixed(2) ?? '—'} ·
                Linea media {selected.summary.avg_line?.toFixed(1) ?? '—'}
              </p>
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-slate-600">
                      <th className="px-2 py-1">Linea</th>
                      <th className="px-2 py-1">Pick</th>
                      <th className="px-2 py-1">Hit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(selected.by_line).map(([ln, cell]) => (
                      <tr key={ln} className="border-b border-slate-100">
                        <td className="px-2 py-1">{ln}</td>
                        <td className="px-2 py-1">{cell.plays}</td>
                        <td className="px-2 py-1">{fmtPct(cell.hit_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="grid gap-2 sm:grid-cols-3 text-xs">
                {Object.entries(selected.walk_forward).map(([seg, cell]) => (
                  <div key={seg} className="rounded border border-slate-100 p-2">
                    <div className="font-medium text-slate-700">{seg.replace(/_/g, ' ')}</div>
                    <div>
                      {cell.picks} pick · {fmtPct(cell.hit_rate)}
                    </div>
                  </div>
                ))}
              </div>
              {selected.filtered_wins_top && selected.filtered_wins_top.length > 0 ? (
                <div>
                  <h4 className="text-xs font-semibold text-slate-800">Top pick filtrate (WIN)</h4>
                  <ul className="mt-1 max-h-32 overflow-y-auto text-xs text-slate-600">
                    {selected.filtered_wins_top.slice(0, 10).map((p, i) => (
                      <li key={i}>
                        G.{String(p.round_number)} {String(p.match)} · linea {String(p.line)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {selected.filtered_losses_top && selected.filtered_losses_top.length > 0 ? (
                <div>
                  <h4 className="text-xs font-semibold text-slate-800">Top pick perse (LOSS)</h4>
                  <ul className="mt-1 max-h-32 overflow-y-auto text-xs text-slate-600">
                    {selected.filtered_losses_top.slice(0, 10).map((p, i) => (
                      <li key={i}>
                        G.{String(p.round_number)} {String(p.match)} · linea {String(p.line)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}

          <p className="text-xs text-slate-500">
            Baseline v1.1: {simulator.baselines.v1_1_cautious_advised.picks} pick ·{' '}
            {fmtPct(simulator.baselines.v1_1_cautious_advised.hit_rate)} — v2.1:{' '}
            {simulator.baselines.v2_1_cautious_advised.picks} pick ·{' '}
            {fmtPct(simulator.baselines.v2_1_cautious_advised.hit_rate)}
          </p>
        </>
      ) : !loading && !error ? (
        <p className="text-sm text-slate-500">Nessun dato per la simulazione.</p>
      ) : null}
    </section>
  )
}
