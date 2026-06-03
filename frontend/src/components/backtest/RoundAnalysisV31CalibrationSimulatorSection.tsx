import { useCallback, useState } from 'react'
import {
  getV31CalibrationSimulator,
  type V31CalibrationSimulator,
  type V31CalibrationSimulatorStrategy,
} from '../../lib/api'

const TABS = [
  { id: 'strategies', label: 'Strategie' },
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

  return (
    <section className="space-y-4 rounded-lg border border-violet-200 bg-violet-50/30 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Simulatore calibrazione v3.1</h2>
          <p className="mt-1 max-w-2xl text-xs text-slate-600">
            Confronta 5 configurazioni sperimentali indipendenti da v1.1/v2.x/v3.0. Usa solo feature
            pre-match del dataset v3.1; le predizioni legacy restano solo per audit.
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
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/80 p-3 text-xs">
              <p className="font-medium text-emerald-800">Strategia consigliata</p>
              <p className="mt-1 text-sm font-semibold text-emerald-900">
                {data.strategies.find((s) => s.key === best?.recommended_strategy)?.label ??
                  best?.recommended_strategy ??
                  '—'}
              </p>
              <p className="text-emerald-700">
                {data.summary.fixtures_count} fixture · giornate {data.summary.round_range}
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
                    <th className="px-2 py-2">MAE</th>
                    <th className="px-2 py-2">Bias</th>
                    <th className="px-2 py-2">Pick</th>
                    <th className="px-2 py-2">W/L</th>
                    <th className="px-2 py-2">Hit%</th>
                    <th className="px-2 py-2">O6.5%</th>
                    <th className="px-2 py-2">O7.5%</th>
                    <th className="px-2 py-2">No bet</th>
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

          {activeTab === 'walkforward' && selected ? (
            <WalkForwardPanel strategy={selected} />
          ) : null}
          {activeTab === 'lines' && selected ? <LinesPanel strategy={selected} /> : null}
          {activeTab === 'nobet' && selected ? <NoBetPanel strategy={selected} /> : null}
          {activeTab === 'reasons' && selected ? <ReasonsPanel strategy={selected} /> : null}
          {activeTab === 'audit' ? <AuditPanel audit={data.audit} /> : null}

          {selected && activeTab !== 'strategies' && activeTab !== 'audit' ? (
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
  return (
    <tr
      className={`cursor-pointer border-t border-slate-100 ${selected ? 'bg-violet-50/50' : 'hover:bg-slate-50'}`}
      onClick={onSelect}
    >
      <td className="px-2 py-2 font-medium text-slate-800">{s.label}</td>
      <td className="px-2 py-2">{fmtNum(m.mae, 3)}</td>
      <td className="px-2 py-2">{fmtNum(m.bias, 3)}</td>
      <td className="px-2 py-2">{m.pick_count ?? 0}</td>
      <td className="px-2 py-2">
        {m.win_count ?? 0}/{m.loss_count ?? 0}
      </td>
      <td className="px-2 py-2">{fmtPct(m.hit_rate)}</td>
      <td className="px-2 py-2">{fmtPct(m.hit_rate_over_6_5)}</td>
      <td className="px-2 py-2">{fmtPct(m.hit_rate_over_7_5)}</td>
      <td className="px-2 py-2">{m.no_bet_count ?? 0}</td>
      <td className="px-2 py-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${verdictBadgeClass(s.verdict)}`}>
          {s.verdict_label}
        </span>
      </td>
    </tr>
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
  const lm = strategy.line_metrics as Record<string, { picks?: number; hit_rate?: number }>
  return (
    <ul className="space-y-1 text-xs">
      {Object.entries(lm).map(([line, cell]) => (
        <li key={line} className="rounded border border-slate-200 bg-white px-3 py-2">
          Linea {line}: {cell.picks ?? 0} pick — hit {fmtPct(cell.hit_rate)}
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
  }
  return (
    <div className="rounded border border-slate-200 bg-white p-3 text-xs text-slate-700">
      <p>No bet / borderline: {bet.no_bet_count ?? 0}</p>
      <p>Borderline: {bet.borderline_count ?? 0}</p>
      <p>Pick GIOCA: {bet.pick_count ?? 0}</p>
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
      <p>Campi vietati usati: {(audit.forbidden_fields_used ?? []).length}</p>
    </div>
  )
}
