import { useCallback, useEffect, useState } from 'react'
import {
  getPredictiveComponentComparisonFixtures,
  getPredictiveComponentComparisonReport,
  type ComponentComparisonReport,
  type ComponentComparisonRow,
} from '../../lib/api'
import { PredictiveComponentComparisonExport } from './PredictiveComponentComparisonExport'
import { PredictiveComponentComparisonTable } from './PredictiveComponentComparisonTable'

const ERROR_DIRECTION_OPTIONS = [
  { value: '', label: 'Tutte le direzioni' },
  { value: 'overestimated', label: 'Sovrastimato' },
  { value: 'underestimated', label: 'Sottostimato' },
  { value: 'aligned', label: 'Allineato' },
  { value: 'not_comparable', label: 'Non confrontabile' },
]

type Props = {
  runId: number | null
}

export function PredictiveComponentComparisonPanel({ runId }: Props) {
  const [rows, setRows] = useState<ComponentComparisonRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [strategyKey, setStrategyKey] = useState('')
  const [roundNumber, setRoundNumber] = useState('')
  const [macroArea, setMacroArea] = useState('')
  const [errorDirection, setErrorDirection] = useState('')
  const [suspiciousOnly, setSuspiciousOnly] = useState(false)
  const [reportSummary, setReportSummary] = useState<ComponentComparisonReport | null>(null)

  const load = useCallback(async () => {
    if (runId == null) return
    setLoading(true)
    setError(null)
    try {
      const [listRes, reportRes] = await Promise.all([
        getPredictiveComponentComparisonFixtures(runId, {
          strategy_key: strategyKey || undefined,
          round_number: roundNumber ? Number(roundNumber) : undefined,
          macro_area: macroArea || undefined,
          error_direction: errorDirection || undefined,
          suspicious_only: suspiciousOnly,
          limit: 300,
        }),
        getPredictiveComponentComparisonReport(runId, {
          detail: 'summary',
          strategy_key: strategyKey || undefined,
          round_number: roundNumber ? Number(roundNumber) : undefined,
        }),
      ])
      setRows(listRes.items)
      setTotal(listRes.total)
      setReportSummary(reportRes)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setRows([])
      setTotal(0)
      setReportSummary(null)
    } finally {
      setLoading(false)
    }
  }, [runId, strategyKey, roundNumber, macroArea, errorDirection, suspiciousOnly])

  useEffect(() => {
    void load()
  }, [load])

  if (runId == null) {
    return (
      <p className="text-sm text-slate-600">
        Esegui o apri un&apos;analisi dallo storico per il confronto Predetto vs Reale.
      </p>
    )
  }

  const seasonStrategies = reportSummary?.season_summary?.strategies ?? {}

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-amber-200 bg-amber-50/80 p-3 text-xs text-amber-950">
        Valori predetti = pre-match. Valori reali e contributi actual* = post-match, solo diagnosi.
        Nessuna modifica ai pesi del modello.
      </div>

      <PredictiveComponentComparisonExport runId={runId} strategyKey={strategyKey || undefined} />

      <div className="flex flex-wrap gap-3 rounded-lg border border-slate-200 bg-white p-4 text-xs">
        <label className="flex flex-col gap-1">
          Strategia
          <input
            className="rounded border border-slate-300 px-2 py-1"
            placeholder="es. v31_bias_corrected"
            value={strategyKey}
            onChange={(e) => setStrategyKey(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          Giornata
          <input
            type="number"
            className="w-20 rounded border border-slate-300 px-2 py-1"
            value={roundNumber}
            onChange={(e) => setRoundNumber(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          Macro-area
          <input
            className="rounded border border-slate-300 px-2 py-1"
            placeholder="offensive_production"
            value={macroArea}
            onChange={(e) => setMacroArea(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          Direzione errore
          <select
            className="rounded border border-slate-300 px-2 py-1"
            value={errorDirection}
            onChange={(e) => setErrorDirection(e.target.value)}
          >
            {ERROR_DIRECTION_OPTIONS.map((o) => (
              <option key={o.value || 'all'} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-end gap-2 self-end">
          <input
            type="checkbox"
            checked={suspiciousOnly}
            onChange={(e) => setSuspiciousOnly(e.target.checked)}
          />
          Solo sospetti
        </label>
        <button
          type="button"
          className="self-end rounded border border-slate-300 px-3 py-1 hover:bg-slate-50"
          onClick={() => void load()}
        >
          Filtra
        </button>
      </div>

      {Object.keys(seasonStrategies).length > 0 ? (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs">
          <h3 className="font-semibold text-slate-800">Riepilogo stagione (per strategia)</h3>
          <ul className="mt-2 space-y-2">
            {Object.entries(seasonStrategies).map(([sk, data]) => (
              <li key={sk}>
                <span className="font-mono text-[10px]">{sk}</span>:{' '}
                {data.top_suspicious_variables?.length ?? 0} variabili sospette in evidenza
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {loading ? <p className="text-xs text-slate-600">Caricamento…</p> : null}
      <p className="text-xs text-slate-600">{total} righe componente (max 300 visualizzate)</p>

      <PredictiveComponentComparisonTable rows={rows} />
    </section>
  )
}
