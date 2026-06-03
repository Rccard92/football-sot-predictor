import { useCallback, useState } from 'react'
import {
  getV31CalibrationSimulator,
  type V31CalibrationSimulator,
  type V31CalibrationSimulatorStrategy,
} from '../../lib/api'

const TABS = [
  { id: 'strategies', label: 'Strategie' },
  { id: 'scale', label: 'Diagnostica scala' },
  { id: 'walkforward', label: 'Walk-forward' },
  { id: 'lines', label: 'Linee' },
  { id: 'nobet', label: 'No bet' },
  { id: 'reasons', label: 'Reason codes' },
  { id: 'audit', label: 'Audit anti-leakage' },
] as const

type TabId = (typeof TABS)[number]['id']

type Props = {
  competitionId: number | null
  seasonYear: number
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v.toFixed(1)}%`
}

function fmtNum(v: number | null | undefined, d = 2): string {
  if (v == null) return '—'
  return v.toFixed(d)
}

function verdictBadgeClass(verdict: string): string {
  switch (verdict) {
    case 'v31_candidate':
      return 'bg-emerald-100 text-emerald-800'
    case 'solid':
      return 'bg-teal-100 text-teal-800'
    case 'promising':
      return 'bg-blue-100 text-blue-800'
    default:
      return 'bg-slate-100 text-slate-700'
  }
}

export function RoundAnalysisV31CalibrationSimulatorSection({
  competitionId,
  seasonYear,
}: Props) {
  const [data, setData] = useState<V31CalibrationSimulator | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('strategies')
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  const run = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    setError(null)
    try {
      const res = await getV31CalibrationSimulator(competitionId, seasonYear, {
        strategy: 'all',
      })
      setData(res)
      setSelectedKey(res.best_by.recommended_strategy ?? res.strategies[0]?.key ?? null)
    } catch (e) {
      setData(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [competitionId, seasonYear])

  if (competitionId == null) return null

  const best = data?.best_by
  const selected = data?.strategies.find((s) => s.key === selectedKey) ?? data?.strategies[0]
  const recLabel =
    data?.summary.recommendation_note ??
    (best?.recommended_strategy
      ? data?.strategies.find((s) => s.key === best.recommended_strategy)?.label
      : null)

  return (
    <section className="space-y-4 rounded-lg border border-violet-200 bg-violet-50/30 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Simulatore calibrazione v3.1</h2>
          <p className="mt-1 max-w-2xl text-xs text-slate-600">
            Base SOT assoluta + correttivi macro. Le predizioni legacy (v1.1–v3.0) non entrano nel
            modello.
          </p>
        </div>
        <button
          type="button"
          disabled={loading}
          className="rounded-lg border border-violet-700 bg-violet-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-600 disabled:opacity-50"
          onClick={() => void run()}
        >
          {loading ? 'Simulazione…' : 'Esegui simulazione v3.1'}
        </button>
      </div>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      {data ? (
        <>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs">
              <p className="font-medium text-slate-500">Miglior MAE</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {best?.mae?.strategy ?? '—'}
              </p>
              <p className="text-slate-600">{fmtNum(best?.mae?.value, 3)}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs">
              <p className="font-medium text-slate-500">Miglior hit rate</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {best?.hit_rate?.strategy ?? '—'}
              </p>
              <p className="text-slate-600">{fmtPct(best?.hit_rate?.value)}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs">
              <p className="font-medium text-slate-500">Miglior equilibrio</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {best?.balanced_score?.strategy ?? '—'}
              </p>
              <p className="text-slate-600">{fmtNum(best?.balanced_score?.value, 2)}</p>
            </div>
            <div
              className={`rounded-lg border p-3 text-xs ${
                best?.all_strategies_zero_picks
                  ? 'border-rose-300 bg-rose-50'
                  : 'border-emerald-200 bg-emerald-50/80'
              }`}
            >
              <p
                className={`font-medium ${
                  best?.all_strategies_zero_picks ? 'text-rose-800' : 'text-emerald-800'
                }`}
              >
                Strategia consigliata
              </p>
              <p
                className={`mt-1 text-sm font-semibold ${
                  best?.all_strategies_zero_picks ? 'text-rose-900' : 'text-emerald-900'
                }`}
              >
                {recLabel ?? '—'}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-1 border-b border-slate-200 pb-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`rounded px-2 py-1 text-xs font-medium ${
                  activeTab === t.id
                    ? 'bg-violet-100 text-violet-900'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
                onClick={() => setActiveTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {activeTab === 'strategies' ? (
            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-2 py-2">Strategia</th>
                    <th className="px-2 py-2">Pred avg</th>
                    <th className="px-2 py-2">Actual avg</th>
                    <th className="px-2 py-2">Scala</th>
                    <th className="px-2 py-2">Pick</th>
                    <th className="px-2 py-2">No bet</th>
                    <th className="px-2 py-2">Hit%</th>
                    <th className="px-2 py-2">MAE</th>
                    <th className="px-2 py-2">Bias</th>
                    <th className="px-2 py-2">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {data.strategies.map((s) => (
                    <StrategyRow
                      key={s.key}
                      s={s}
                      selected={selectedKey === s.key}
                      onSelect={() => setSelectedKey(s.key)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {activeTab === 'scale' && selected ? (
            <ScaleDiagnosticsPanel strategy={selected} />
          ) : null}

          {activeTab === 'walkforward' && selected ? (
            <WalkForwardPanel strategy={selected} />
          ) : null}
          {activeTab === 'lines' && selected ? <LinesPanel strategy={selected} /> : null}
          {activeTab === 'nobet' && selected ? <NoBetPanel strategy={selected} /> : null}
          {activeTab === 'reasons' && selected ? <ReasonsPanel strategy={selected} /> : null}
          {activeTab === 'audit' ? <AuditPanel audit={data.audit} /> : null}

          {selected && activeTab !== 'strategies' && activeTab !== 'scale' && activeTab !== 'audit' ? (
            <p className="text-[10px] text-slate-500">
              Dettaglio: {selected.label}{' '}
              <button
                type="button"
                className="text-violet-700 underline"
                onClick={() => setActiveTab('strategies')}
              >
                cambia strategia
              </button>
            </p>
          ) : null}
        </>
      ) : null}
    </section>
  )
}

function StrategyRow({
  s,
  selected,
  onSelect,
}: {
  s: V31CalibrationSimulatorStrategy
  selected: boolean
  onSelect: () => void
}) {
  const m = s.metrics
  const scaleWarn = m.scale_warning ?? s.prediction_diagnostics?.scale_warning
  return (
    <tr
      className={`cursor-pointer border-t border-slate-100 ${selected ? 'bg-violet-50/50' : 'hover:bg-slate-50'}`}
      onClick={onSelect}
    >
      <td className="px-2 py-2 font-medium text-slate-800">{s.label}</td>
      <td className="px-2 py-2">{fmtNum(m.predicted_total_avg ?? s.prediction_diagnostics?.predicted_total_avg, 2)}</td>
      <td className="px-2 py-2">{fmtNum(m.actual_total_avg ?? s.prediction_diagnostics?.actual_total_avg, 2)}</td>
      <td className="px-2 py-2">
        {scaleWarn ? (
          <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-medium text-rose-800">
            Fuori scala
          </span>
        ) : (
          <span className="text-emerald-700">OK</span>
        )}
      </td>
      <td className="px-2 py-2">{m.pick_count ?? 0}</td>
      <td className="px-2 py-2">{m.no_bet_count ?? 0}</td>
      <td className="px-2 py-2">{fmtPct(m.hit_rate)}</td>
      <td className="px-2 py-2">{fmtNum(m.mae, 3)}</td>
      <td className="px-2 py-2">{fmtNum(m.bias, 3)}</td>
      <td className="px-2 py-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${verdictBadgeClass(s.verdict)}`}>
          {s.verdict_label}
        </span>
      </td>
    </tr>
  )
}

function ScaleDiagnosticsPanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const d = strategy.prediction_diagnostics
  if (!d) return <p className="text-xs text-slate-500">Nessuna diagnostica.</p>
  return (
    <div className="rounded border border-slate-200 bg-white p-3 text-xs text-slate-700">
      <p className="font-medium text-slate-900">{strategy.label}</p>
      {d.scale_warning ? (
        <p className="mt-1 font-medium text-rose-800">
          Fuori scala — {(d.warnings ?? []).join(', ')}
        </p>
      ) : (
        <p className="mt-1 text-emerald-700">Scala predizione nella norma attesa.</p>
      )}
      <ul className="mt-2 grid gap-1 sm:grid-cols-2">
        <li>Pred avg: {fmtNum(d.predicted_total_avg, 2)}</li>
        <li>Actual avg: {fmtNum(d.actual_total_avg, 2)}</li>
        <li>Pred min/max: {fmtNum(d.predicted_total_min, 1)} / {fmtNum(d.predicted_total_max, 1)}</li>
        <li>Actual min/max: {fmtNum(d.actual_total_min, 1)} / {fmtNum(d.actual_total_max, 1)}</li>
        <li>Pred &lt; 3: {d.predicted_under_3_count ?? 0}</li>
        <li>Pred &gt; 12: {d.predicted_over_12_count ?? 0}</li>
      </ul>
    </div>
  )
}

function WalkForwardPanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const wf = strategy.walk_forward_metrics as Record<
    string,
    {
      test_rounds?: string
      test_regression?: { mae?: number }
      test_betting?: { hit_rate?: number; pick_count?: number }
    }
  >
  return (
    <div className="space-y-2 text-xs text-slate-700">
      {Object.entries(wf).map(([k, v]) => (
        <div key={k} className="rounded border border-slate-200 bg-white p-3">
          <p className="font-medium">{k}</p>
          <p>Test giornate {v.test_rounds}</p>
          <p>MAE test: {fmtNum(v.test_regression?.mae, 3)}</p>
          <p>
            Hit rate test: {fmtPct(v.test_betting?.hit_rate)} ({v.test_betting?.pick_count ?? 0}{' '}
            pick)
          </p>
        </div>
      ))}
    </div>
  )
}

function LinesPanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const lm = strategy.line_metrics as Record<
    string,
    {
      picks?: number
      wins?: number
      losses?: number
      hit_rate?: number
      avg_estimated_prob?: number
      avg_margin?: number
    }
  >
  return (
    <ul className="space-y-1 text-xs">
      {Object.entries(lm).map(([line, cell]) => (
        <li key={line} className="rounded border border-slate-200 bg-white px-3 py-2">
          Linea {line}: {cell.picks ?? 0} pick — W/L {cell.wins ?? 0}/{cell.losses ?? 0} — hit{' '}
          {fmtPct(cell.hit_rate)} — prob media {fmtNum((cell.avg_estimated_prob ?? 0) * 100, 1)}% —
          margine medio {fmtNum(cell.avg_margin, 2)}
        </li>
      ))}
    </ul>
  )
}

function NoBetPanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const bet = strategy.betting_metrics as {
    no_bet_count?: number
    borderline_count?: number
    pick_count?: number
    no_bet_samples?: Array<{
      fixture_id?: number
      match?: string
      predicted_total_sot?: number
      reason_codes?: string[]
    }>
  }
  const top = Object.entries(strategy.reason_code_counts ?? {}).slice(0, 8)
  return (
    <div className="space-y-2 text-xs text-slate-700">
      <div className="rounded border border-slate-200 bg-white p-3">
        <p>No bet / borderline: {bet.no_bet_count ?? 0}</p>
        <p>Borderline: {bet.borderline_count ?? 0}</p>
        <p>Pick GIOCA: {bet.pick_count ?? 0}</p>
      </div>
      <div className="rounded border border-slate-200 bg-white p-3">
        <p className="font-medium">Top reason codes (no bet)</p>
        <ul className="mt-1 font-mono text-[10px]">
          {top.map(([code, n]) => (
            <li key={code}>
              {code}: {n}
            </li>
          ))}
        </ul>
      </div>
      {(bet.no_bet_samples ?? []).length > 0 ? (
        <div className="rounded border border-slate-200 bg-white p-3">
          <p className="font-medium">Esempi no bet</p>
          <ul className="mt-1 space-y-1">
            {bet.no_bet_samples?.map((s) => (
              <li key={s.fixture_id}>
                {s.match} — pred {s.predicted_total_sot} — {(s.reason_codes ?? []).join(', ')}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

function ReasonsPanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const counts = strategy.reason_code_counts ?? {}
  return (
    <ul className="max-h-48 overflow-y-auto text-xs text-slate-700">
      {Object.entries(counts).map(([code, n]) => (
        <li key={code} className="flex justify-between border-b border-slate-100 py-1">
          <span className="font-mono text-[10px]">{code}</span>
          <span>{n}</span>
        </li>
      ))}
    </ul>
  )
}

function AuditPanel({ audit }: { audit: V31CalibrationSimulator['audit'] }) {
  return (
    <div className="rounded border border-emerald-200 bg-emerald-50/60 p-3 text-xs text-emerald-900">
      <p>Anti-leakage: {audit.anti_leakage ? 'OK' : 'FAILED'}</p>
      <p>Legacy predictions come feature: {audit.legacy_predictions_used_as_features ? 'sì' : 'no'}</p>
      <p>Target usato come input: {audit.target_used_as_input === false ? 'no' : 'sì'}</p>
      <p>Campi vietati usati: {(audit.forbidden_fields_used ?? []).length}</p>
    </div>
  )
}
