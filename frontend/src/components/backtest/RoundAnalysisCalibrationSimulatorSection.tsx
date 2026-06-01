import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getRoundAnalysisCalibrationSimulator,
  getRoundAnalysisCalibrationSimulatorReportJson,
  type CalibrationSimulatorLossDiagnostic,
  type CalibrationSimulatorStrategyBlock,
  type RoundAnalysisCalibrationSimulator,
} from '../../lib/api'

const TABS = [
  { id: 'strategies', label: 'Strategie' },
  { id: 'lines', label: 'Linee' },
  { id: 'risk', label: 'Low-total risk' },
  { id: 'losses', label: 'Loss diagnostics' },
  { id: 'reasons', label: 'Reason codes' },
  { id: 'walkforward', label: 'Walk-forward' },
] as const

type TabId = (typeof TABS)[number]['id']

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

function verdictBadge(verdict: string | undefined): string {
  switch (verdict) {
    case 'excellent':
      return 'bg-emerald-100 text-emerald-800'
    case 'promising':
      return 'bg-teal-100 text-teal-800'
    case 'balanced':
      return 'bg-blue-100 text-blue-800'
    case 'too_selective':
      return 'bg-amber-100 text-amber-800'
    case 'weak':
      return 'bg-rose-100 text-rose-800'
    default:
      return 'bg-slate-100 text-slate-700'
  }
}

function verdictLabel(verdict: string | undefined): string {
  switch (verdict) {
    case 'excellent':
      return 'Eccellente'
    case 'promising':
      return 'Promettente'
    case 'balanced':
      return 'Equilibrata'
    case 'too_selective':
      return 'Troppo selettiva'
    case 'weak':
      return 'Debole'
    default:
      return 'Neutrale'
  }
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
  const [activeTab, setActiveTab] = useState<TabId>('strategies')
  const [lossSort, setLossSort] = useState<'round' | 'gap' | 'risk'>('round')
  const [downloadingJson, setDownloadingJson] = useState(false)

  const load = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    setError(null)
    try {
      const data = await getRoundAnalysisCalibrationSimulator(competitionId, seasonYear)
      setSimulator(data)
      const first = Object.keys(data.strategies)[0]
      setSelectedStrategy(
        data.ranking.best_hit_rate_sufficient_volume ??
          data.ranking.best_hit_rate ??
          first ??
          null,
      )
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

  const selectedStrategyBlock = useMemo((): CalibrationSimulatorStrategyBlock | null => {
    if (!simulator || !selectedStrategy) return null
    return simulator.strategies[selectedStrategy] ?? null
  }, [simulator, selectedStrategy])

  const sortedLosses = useMemo(() => {
    const diagnostics = selectedStrategyBlock?.loss_diagnostics ?? []
    if (!diagnostics.length) return []
    const rows = [...diagnostics]
    rows.sort((a, b) => {
      if (lossSort === 'gap') {
        const ga = Math.abs(a.prediction_gap_v21_minus_v11 ?? 0)
        const gb = Math.abs(b.prediction_gap_v21_minus_v11 ?? 0)
        return gb - ga
      }
      if (lossSort === 'risk') {
        return (b.low_total_risk_v2_score ?? 0) - (a.low_total_risk_v2_score ?? 0)
      }
      return (a.round_number ?? 0) - (b.round_number ?? 0)
    })
    return rows
  }, [selectedStrategyBlock, lossSort])

  if (competitionId == null) return null

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Simulatore calibrazione v3.0</h2>
          <p className="text-xs text-slate-500">
            Value selector v3.0-C — simulazione read-only, nessun ricalcolo predizioni
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
                Miglior hit rate:{' '}
                {strategyLabel(
                  simulator.ranking.best_hit_rate,
                  simulator.strategies[simulator.ranking.best_hit_rate],
                )}
              </span>
            ) : null}
            {simulator.ranking.best_hit_rate_sufficient_volume ? (
              <span className="rounded-full bg-emerald-50 px-2 py-1 text-emerald-900 ring-1 ring-emerald-200">
                Hit rate (≥60 pick):{' '}
                {strategyLabel(
                  simulator.ranking.best_hit_rate_sufficient_volume,
                  simulator.strategies[simulator.ranking.best_hit_rate_sufficient_volume],
                )}
              </span>
            ) : null}
            {simulator.ranking.most_balanced ? (
              <span className="rounded-full bg-violet-100 px-2 py-1 text-violet-800">
                Più equilibrata:{' '}
                {strategyLabel(
                  simulator.ranking.most_balanced,
                  simulator.strategies[simulator.ranking.most_balanced],
                )}
              </span>
            ) : null}
            {simulator.ranking.too_selective ? (
              <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-800">
                Troppo selettiva:{' '}
                {strategyLabel(
                  simulator.ranking.too_selective,
                  simulator.strategies[simulator.ranking.too_selective],
                )}
              </span>
            ) : null}
            {simulator.ranking.weakest ? (
              <span className="rounded-full bg-rose-100 px-2 py-1 text-rose-800">
                Più debole:{' '}
                {strategyLabel(
                  simulator.ranking.weakest,
                  simulator.strategies[simulator.ranking.weakest],
                )}
              </span>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-1 border-b border-slate-200">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`px-3 py-2 text-xs font-medium ${
                  activeTab === tab.id
                    ? 'border-b-2 border-slate-900 text-slate-900'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === 'strategies' ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-slate-600">
                    <th className="px-2 py-2">Strategia</th>
                    <th className="px-2 py-2">Verdict</th>
                    <th className="px-2 py-2">Pick</th>
                    <th className="px-2 py-2">W/L</th>
                    <th className="px-2 py-2">Hit%</th>
                    <th className="px-2 py-2">Δ v2.1</th>
                    <th className="px-2 py-2">Δ v1.1</th>
                    <th className="px-2 py-2">Evitate</th>
                    <th className="px-2 py-2">Perse</th>
                    <th className="px-2 py-2">Linea avg</th>
                    <th className="px-2 py-2">WF min</th>
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
                      <td className="px-2 py-2">
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${verdictBadge(block.strategy_verdict)}`}
                        >
                          {verdictLabel(block.strategy_verdict)}
                        </span>
                      </td>
                      <td className="px-2 py-2">{block.summary.picks}</td>
                      <td className="px-2 py-2">
                        {block.summary.wins}/{block.summary.losses}
                      </td>
                      <td className="px-2 py-2">{fmtPct(block.summary.hit_rate)}</td>
                      <td className="px-2 py-2">{fmtDelta(block.vs_v2_1_baseline.delta_hit_rate)}</td>
                      <td className="px-2 py-2">{fmtDelta(block.vs_v1_1_baseline.delta_hit_rate)}</td>
                      <td className="px-2 py-2">{block.vs_v2_1_baseline.avoided_losses}</td>
                      <td className="px-2 py-2">{block.vs_v2_1_baseline.missed_wins}</td>
                      <td className="px-2 py-2">{block.summary.avg_line?.toFixed(1) ?? '—'}</td>
                      <td className="px-2 py-2">{fmtPct(block.walk_forward_stability)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {selectedStrategyBlock ? (
            <>
              <p className="text-xs text-slate-600">
                Strategia selezionata: <span className="font-medium">{selectedStrategyBlock.label}</span>
                {selectedStrategy !== activeTab && activeTab !== 'strategies' ? (
                  <button
                    type="button"
                    className="ml-2 text-slate-500 underline"
                    onClick={() => setActiveTab('strategies')}
                  >
                    Cambia strategia
                  </button>
                ) : null}
              </p>

              {activeTab === 'lines' ? (
                <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white p-4">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-left text-slate-600">
                        <th className="px-2 py-1">Linea</th>
                        <th className="px-2 py-1">Pick</th>
                        <th className="px-2 py-1">W/L</th>
                        <th className="px-2 py-1">Hit%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(selectedStrategyBlock.by_line).map(([ln, cell]) => (
                        <tr key={ln} className="border-b border-slate-100">
                          <td className="px-2 py-1">{ln}</td>
                          <td className="px-2 py-1">{cell.plays}</td>
                          <td className="px-2 py-1">
                            {cell.wins}/{cell.losses}
                          </td>
                          <td className="px-2 py-1">{fmtPct(cell.hit_rate)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}

              {activeTab === 'risk' ? (
                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                    <h3 className="text-sm font-semibold text-slate-900">low_total_risk_v2</h3>
                    <table className="mt-2 min-w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 text-left text-slate-600">
                          <th className="px-2 py-1">Bucket</th>
                          <th className="px-2 py-1">Pick</th>
                          <th className="px-2 py-1">Hit%</th>
                          <th className="px-2 py-1">Low total reale</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(selectedStrategyBlock.by_low_total_risk_v2 ?? {}).map(([bucket, cell]) => (
                          <tr key={bucket} className="border-b border-slate-100">
                            <td className="px-2 py-1 font-medium">{bucket}</td>
                            <td className="px-2 py-1">{cell.picks}</td>
                            <td className="px-2 py-1">{fmtPct(cell.hit_rate)}</td>
                            <td className="px-2 py-1">{fmtPct(cell.actual_low_total_rate)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                    <h3 className="text-sm font-semibold text-slate-900">Fasce SOT reali</h3>
                    <table className="mt-2 min-w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 text-left text-slate-600">
                          <th className="px-2 py-1">Fascia</th>
                          <th className="px-2 py-1">Pick</th>
                          <th className="px-2 py-1">Hit%</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(selectedStrategyBlock.by_sot_bucket).map(([bucket, cell]) => (
                          <tr key={bucket} className="border-b border-slate-100">
                            <td className="px-2 py-1">{bucket}</td>
                            <td className="px-2 py-1">{cell.picks}</td>
                            <td className="px-2 py-1">{fmtPct(cell.hit_rate)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              {activeTab === 'losses' ? (
                <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold text-slate-900">
                      Perdite ({selectedStrategyBlock.loss_diagnostics?.length ?? 0})
                    </h3>
                    <select
                      className="rounded border border-slate-200 px-2 py-1 text-xs"
                      value={lossSort}
                      onChange={(e) => setLossSort(e.target.value as typeof lossSort)}
                    >
                      <option value="round">Ordina per giornata</option>
                      <option value="gap">Ordina per gap v2.1−v1.1</option>
                      <option value="risk">Ordina per risk_v2</option>
                    </select>
                  </div>
                  {sortedLosses.length === 0 ? (
                    <p className="text-xs text-slate-500">
                      Nessuna perdita disponibile per questa strategia.
                    </p>
                  ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 text-left text-slate-600">
                          <th className="px-2 py-1">G.</th>
                          <th className="px-2 py-1">Partita</th>
                          <th className="px-2 py-1">Linea</th>
                          <th className="px-2 py-1">SOT</th>
                          <th className="px-2 py-1">Gap</th>
                          <th className="px-2 py-1">Risk v2</th>
                          <th className="px-2 py-1">WMM</th>
                          <th className="px-2 py-1">Conf.</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sortedLosses.map((row: CalibrationSimulatorLossDiagnostic, i) => (
                          <tr key={i} className="border-b border-slate-100">
                            <td className="px-2 py-1">{row.round_number}</td>
                            <td className="px-2 py-1">{row.match}</td>
                            <td className="px-2 py-1">{row.selected_line ?? row.line}</td>
                            <td className="px-2 py-1">{row.actual_total_sot}</td>
                            <td className="px-2 py-1">
                              {row.prediction_gap_v21_minus_v11?.toFixed(2) ?? '—'}
                            </td>
                            <td className="px-2 py-1">
                              {row.low_total_risk_v2_bucket} ({row.low_total_risk_v2_score})
                            </td>
                            <td className="px-2 py-1">
                              {row.v21_macros?.weighted_macro_multiplier_avg?.toFixed(2) ?? '—'}
                            </td>
                            <td className="px-2 py-1">{row.confidence || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  )}
                </div>
              ) : null}

              {activeTab === 'reasons' ? (
                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <h3 className="text-sm font-semibold text-slate-900">Reason codes</h3>
                  {Object.keys(selectedStrategyBlock.by_reason_codes ?? {}).length === 0 ? (
                    <p className="mt-2 text-xs text-slate-500">
                      Nessun reason code per questa strategia (principalmente hybrid).
                    </p>
                  ) : (
                    <table className="mt-2 min-w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 text-left text-slate-600">
                          <th className="px-2 py-1">Code</th>
                          <th className="px-2 py-1">Conteggio</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(selectedStrategyBlock.by_reason_codes ?? {})
                          .sort((a, b) => b[1] - a[1])
                          .map(([code, count]) => (
                            <tr key={code} className="border-b border-slate-100">
                              <td className="px-2 py-1 font-mono">{code}</td>
                              <td className="px-2 py-1">{count}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  )}
                  {selectedStrategyBlock.by_confidence_tier &&
                  Object.keys(selectedStrategyBlock.by_confidence_tier).length > 0 ? (
                    <div className="mt-4">
                      <h4 className="text-xs font-semibold text-slate-800">Confidence tier</h4>
                      <div className="mt-1 flex flex-wrap gap-2">
                        {Object.entries(selectedStrategyBlock.by_confidence_tier).map(([tier, cell]) => (
                          <span
                            key={tier}
                            className="rounded border border-slate-200 px-2 py-1 text-xs"
                          >
                            {tier}: {cell.picks} pick · {fmtPct(cell.hit_rate)}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {selectedStrategyBlock.no_bet_audit && selectedStrategyBlock.no_bet_audit.length > 0 ? (
                    <div className="mt-4">
                      <h4 className="text-xs font-semibold text-slate-800">
                        No-bet audit (hybrid, top {selectedStrategyBlock.no_bet_audit.length})
                      </h4>
                      <ul className="mt-1 max-h-40 overflow-y-auto text-xs text-slate-600">
                        {selectedStrategyBlock.no_bet_audit.slice(0, 20).map((row, i) => (
                          <li key={i}>
                            {row.match} — {row.no_bet_reason}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {activeTab === 'walkforward' ? (
                <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
                  <p className="text-xs text-slate-600">
                    Stabilità walk-forward (hit minimo tra segmenti):{' '}
                    <span className="font-medium">{fmtPct(selectedStrategyBlock.walk_forward_stability)}</span>
                  </p>
                  <div className="grid gap-2 sm:grid-cols-3 text-xs">
                    {Object.entries(selectedStrategyBlock.walk_forward).map(([seg, cell]) => (
                      <div key={seg} className="rounded border border-slate-100 p-2">
                        <div className="font-medium text-slate-700">{seg.replace(/_/g, ' ')}</div>
                        <div>
                          {cell.picks} pick · {cell.wins}W/{cell.losses}L · {fmtPct(cell.hit_rate)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </>
          ) : null}

          <p className="text-xs text-slate-500">
            Baseline v1.1: {simulator.baselines.v1_1_cautious_advised.picks} pick ·{' '}
            {fmtPct(simulator.baselines.v1_1_cautious_advised.hit_rate)} — v2.1:{' '}
            {simulator.baselines.v2_1_cautious_advised.picks} pick ·{' '}
            {fmtPct(simulator.baselines.v2_1_cautious_advised.hit_rate)} ·{' '}
            {Object.keys(simulator.strategies).length} strategie simulate
          </p>
        </>
      ) : !loading && !error ? (
        <p className="text-sm text-slate-500">Nessun dato per la simulazione.</p>
      ) : null}
    </section>
  )
}
