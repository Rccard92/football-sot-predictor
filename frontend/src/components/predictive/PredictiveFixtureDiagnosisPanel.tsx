import { Fragment, useCallback, useEffect, useState } from 'react'
import {
  getPredictiveSimulatorFixtures,
  postPredictiveFixtureNote,
  type PredictiveFixturePrediction,
} from '../../lib/api'

const OUTCOME_OPTIONS = [
  { value: '', label: 'Tutti gli outcome' },
  { value: 'healthy_win', label: 'Healthy win' },
  { value: 'understated_win', label: 'Understated win' },
  { value: 'high_missed', label: 'High missed' },
  { value: 'false_high_prediction', label: 'False high' },
  { value: 'bad_loss_overestimation', label: 'Bad loss overestimation' },
  { value: 'extreme_win_outlier', label: 'Extreme outlier' },
]

type Props = {
  runId: number | null
  onAnalyzeFixture?: (fixtureId: number, strategyKey: string) => void
}

export function PredictiveFixtureDiagnosisPanel({ runId, onAnalyzeFixture }: Props) {
  const [items, setItems] = useState<PredictiveFixturePrediction[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [strategyKey, setStrategyKey] = useState('')
  const [outcomeType, setOutcomeType] = useState('')
  const [minAbsError, setMinAbsError] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [noteDraft, setNoteDraft] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    if (runId == null) return
    setLoading(true)
    setError(null)
    try {
      const res = await getPredictiveSimulatorFixtures(runId, {
        strategy_key: strategyKey || undefined,
        outcome_type: outcomeType || undefined,
        min_abs_error: minAbsError ? Number(minAbsError) : undefined,
        sort_by: 'abs_error',
        sort_dir: 'desc',
        limit: 100,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [runId, strategyKey, outcomeType, minAbsError])

  useEffect(() => {
    void load()
  }, [load])

  const saveNote = async (row: PredictiveFixturePrediction) => {
    if (runId == null) return
    const key = `${row.fixture_id}:${row.strategy_key}`
    const note = noteDraft[key] ?? row.user_note ?? ''
    if (!note.trim()) return
    await postPredictiveFixtureNote(runId, row.fixture_id, {
      strategy_key: row.strategy_key,
      note: note.trim(),
    })
    void load()
  }

  if (runId == null) {
    return (
      <p className="text-sm text-slate-600">
        Esegui o apri un&apos;analisi dallo storico per vedere la diagnosi fixture-by-fixture.
      </p>
    )
  }

  return (
    <section className="space-y-4">
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
          Outcome
          <select
            className="rounded border border-slate-300 px-2 py-1"
            value={outcomeType}
            onChange={(e) => setOutcomeType(e.target.value)}
          >
            {OUTCOME_OPTIONS.map((o) => (
              <option key={o.value || 'all'} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          Min |errore|
          <input
            type="number"
            step="0.1"
            className="w-24 rounded border border-slate-300 px-2 py-1"
            value={minAbsError}
            onChange={(e) => setMinAbsError(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="self-end rounded border border-slate-300 px-3 py-1 hover:bg-slate-50"
          onClick={() => void load()}
        >
          Filtra
        </button>
      </div>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {loading ? <p className="text-xs text-slate-600">Caricamento fixture…</p> : null}

      <p className="text-xs text-slate-600">{total} righe totali (max 100 visualizzate)</p>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-700">
            <tr>
              <th className="px-2 py-2">G</th>
              <th className="px-2 py-2">Match</th>
              <th className="px-2 py-2">Strategia</th>
              <th className="px-2 py-2">Prev</th>
              <th className="px-2 py-2">Reale</th>
              <th className="px-2 py-2">Err</th>
              <th className="px-2 py-2">Bucket</th>
              <th className="px-2 py-2">Outcome</th>
              <th className="px-2 py-2">Motivo</th>
              <th className="px-2 py-2">Nota</th>
              <th className="px-2 py-2">AI</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => {
              const rowKey = `${row.fixture_id}:${row.strategy_key}`
              const isOpen = expanded === row.fixture_id
              return (
                <Fragment key={rowKey}>
                  <tr key={rowKey} className="border-b border-slate-100 hover:bg-slate-50/50">
                    <td className="px-2 py-2">{row.round_number}</td>
                    <td className="px-2 py-2">{row.match}</td>
                    <td className="px-2 py-2 font-mono text-[10px]">{row.strategy_key}</td>
                    <td className="px-2 py-2">{row.predicted_total_sot?.toFixed(1) ?? '—'}</td>
                    <td className="px-2 py-2">{row.actual_total_sot?.toFixed(1) ?? '—'}</td>
                    <td className="px-2 py-2">{row.abs_error?.toFixed(2) ?? '—'}</td>
                    <td className="px-2 py-2">
                      {row.predicted_bucket}/{row.actual_bucket}
                    </td>
                    <td className="px-2 py-2">
                      <span className="rounded bg-slate-100 px-1 py-0.5">{row.outcome_type ?? row.win_quality ?? '—'}</span>
                    </td>
                    <td className="max-w-[200px] px-2 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(row.reason_codes ?? []).slice(0, 2).map((rc) => (
                          <span
                            key={rc.code}
                            className="rounded bg-amber-100 px-1 py-0.5 text-[10px] text-amber-900"
                            title={rc.evidence}
                          >
                            {rc.label_it}
                          </span>
                        ))}
                      </div>
                      <button
                        type="button"
                        className="mt-1 text-violet-700 underline"
                        onClick={() => setExpanded(isOpen ? null : row.fixture_id)}
                      >
                        {isOpen ? 'Chiudi' : 'Dettaglio'}
                      </button>
                    </td>
                    <td className="px-2 py-2">
                      <input
                        className="w-28 rounded border border-slate-300 px-1 py-0.5"
                        placeholder="Nota"
                        value={noteDraft[rowKey] ?? row.user_note ?? ''}
                        onChange={(e) =>
                          setNoteDraft((d) => ({ ...d, [rowKey]: e.target.value }))
                        }
                      />
                      <button
                        type="button"
                        className="ml-1 text-violet-700"
                        onClick={() => void saveNote(row)}
                      >
                        Salva
                      </button>
                    </td>
                    <td className="px-2 py-2">
                      {onAnalyzeFixture ? (
                        <button
                          type="button"
                          className="whitespace-nowrap text-violet-700 underline"
                          onClick={() => onAnalyzeFixture(row.fixture_id, row.strategy_key)}
                        >
                          Analizza con AI
                        </button>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                  {isOpen ? (
                    <tr key={`${rowKey}-detail`} className="bg-slate-50/80">
                      <td colSpan={11} className="px-4 py-3 text-xs text-slate-700">
                        <p className="font-medium">{row.probable_reason}</p>
                        <ul className="mt-2 list-disc pl-4">
                          {(row.reason_codes ?? []).map((rc) => (
                            <li key={rc.code}>
                              <strong>{rc.label_it}</strong>: {rc.evidence} — {rc.suggested_action}
                            </li>
                          ))}
                        </ul>
                        {row.feature_snapshot ? (
                          <pre className="mt-2 overflow-x-auto rounded bg-white p-2 text-[10px]">
                            {JSON.stringify(row.feature_snapshot, null, 2)}
                          </pre>
                        ) : null}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
