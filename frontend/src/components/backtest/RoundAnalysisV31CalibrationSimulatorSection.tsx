import { useCallback, useState } from 'react'
import {
  getV31CalibrationSimulator,
  getV31CalibrationSimulatorReportJson,
  type V31CalibrationSimulator,
  type V31CalibrationSimulatorStrategy,
} from '../../lib/api'

const TABS = [
  { id: 'strategies', label: 'Strategie' },
  { id: 'accuracy', label: 'Accuratezza' },
  { id: 'coverage', label: 'Coverage WIN' },
  { id: 'errors', label: 'Errori peggiori' },
  { id: 'walkforward', label: 'Walk-forward' },
  { id: 'weights', label: 'Pesi e variabili' },
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
    case 'solid':
      return 'bg-emerald-100 text-emerald-800'
    case 'candidate':
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
  const [exporting, setExporting] = useState(false)
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

  const downloadReport = useCallback(async () => {
    if (competitionId == null) return
    setExporting(true)
    try {
      const payload = await getV31CalibrationSimulatorReportJson(competitionId, seasonYear, {
        strategy: 'all',
      })
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `v31-predictive-simulator-${competitionId}-${seasonYear}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setExporting(false)
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
          <h2 className="text-lg font-semibold text-slate-900">Simulatore predittivo v3.1</h2>
          <p className="mt-1 max-w-2xl text-xs text-slate-600">
            Confronta strategie numeriche indipendenti. Ogni strategia predice il totale SOT di tutte
            le partite. La fase bet/no bet verrà costruita dopo.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={loading}
            className="rounded-lg border border-violet-700 bg-violet-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-600 disabled:opacity-50"
            onClick={() => void run()}
          >
            {loading ? 'Simulazione…' : 'Esegui simulazione v3.1'}
          </button>
          <button
            type="button"
            disabled={exporting || !data}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => void downloadReport()}
          >
            {exporting ? 'Export…' : 'Scarica report JSON'}
          </button>
        </div>
      </div>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      {data ? (
        <>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            <KpiCard title="Miglior MAE" strategy={best?.mae?.strategy} value={fmtNum(best?.mae?.value, 3)} />
            <KpiCard
              title="Miglior Bias"
              strategy={best?.bias_near_zero?.strategy}
              value={fmtNum(best?.bias_near_zero?.value, 3)}
            />
            <KpiCard
              title="Miglior vicinanza ±1.5"
              strategy={best?.within_1_5_pct?.strategy}
              value={fmtPct(best?.within_1_5_pct?.value)}
            />
            <KpiCard
              title="Miglior coverage win"
              strategy={best?.coverage_win_rate?.strategy}
              value={fmtPct(best?.coverage_win_rate?.value)}
            />
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/80 p-3 text-xs">
              <p className="font-medium text-emerald-800">Strategia consigliata</p>
              <p className="mt-1 text-sm font-semibold text-emerald-900">{recLabel ?? '—'}</p>
              {best?.balanced_prediction_score?.value != null ? (
                <p className="text-emerald-700">
                  Score {fmtNum(best.balanced_prediction_score.value, 1)}
                </p>
              ) : null}
            </div>
          </div>

          <p className="text-[10px] text-slate-500">
            Fixture: {data.summary.fixtures_count} · Strategie: {data.summary.strategies_run} · Fase:{' '}
            {data.summary.phase ?? 'predictive_numeric'}
          </p>

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
                    <th className="px-2 py-2">MAE</th>
                    <th className="px-2 py-2">RMSE</th>
                    <th className="px-2 py-2">Bias</th>
                    <th className="px-2 py-2">±1.0</th>
                    <th className="px-2 py-2">±1.5</th>
                    <th className="px-2 py-2">Coverage W/L</th>
                    <th className="px-2 py-2">Coverage %</th>
                    <th className="px-2 py-2">Score</th>
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

          {activeTab === 'accuracy' && selected ? <AccuracyPanel strategy={selected} /> : null}
          {activeTab === 'coverage' && selected ? <CoveragePanel strategy={selected} /> : null}
          {activeTab === 'errors' && selected ? <WorstErrorsPanel strategy={selected} /> : null}
          {activeTab === 'walkforward' && selected ? <WalkForwardPanel strategy={selected} /> : null}
          {activeTab === 'weights' && selected ? <WeightsPanel strategy={selected} /> : null}
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

function KpiCard({
  title,
  strategy,
  value,
}: {
  title: string
  strategy?: string | null
  value: string
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs">
      <p className="font-medium text-slate-500">{title}</p>
      <p className="mt-1 text-sm font-semibold text-slate-900">{strategy ?? '—'}</p>
      <p className="text-slate-600">{value}</p>
    </div>
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
  const pm = s.predictive_metrics
  const covW = m.coverage_win_count ?? pm?.coverage_win_count ?? 0
  const covL = m.coverage_loss_count ?? pm?.coverage_loss_count ?? 0
  return (
    <tr
      className={`cursor-pointer border-t border-slate-100 ${selected ? 'bg-violet-50/50' : 'hover:bg-slate-50'}`}
      onClick={onSelect}
    >
      <td className="px-2 py-2 font-medium text-slate-800">{s.label}</td>
      <td className="px-2 py-2">{fmtNum(m.predicted_avg ?? m.predicted_total_avg, 2)}</td>
      <td className="px-2 py-2">{fmtNum(m.actual_avg ?? m.actual_total_avg, 2)}</td>
      <td className="px-2 py-2">{fmtNum(m.mae, 3)}</td>
      <td className="px-2 py-2">{fmtNum(m.rmse, 3)}</td>
      <td className="px-2 py-2">{fmtNum(m.bias, 3)}</td>
      <td className="px-2 py-2">{fmtPct(m.within_1_0_pct ?? pm?.within_1_0_pct)}</td>
      <td className="px-2 py-2">{fmtPct(m.within_1_5_pct ?? pm?.within_1_5_pct)}</td>
      <td className="px-2 py-2">
        {covW}/{covL}
      </td>
      <td className="px-2 py-2">{fmtPct(m.coverage_win_rate ?? pm?.coverage_win_rate)}</td>
      <td className="px-2 py-2">{fmtNum(s.balanced_prediction_score, 1)}</td>
      <td className="px-2 py-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${verdictBadgeClass(s.verdict)}`}>
          {s.verdict_label}
        </span>
      </td>
    </tr>
  )
}

function AccuracyPanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const pm = strategy.predictive_metrics
  const d = strategy.prediction_diagnostics
  return (
    <div className="rounded border border-slate-200 bg-white p-3 text-xs text-slate-700">
      <p className="font-medium text-slate-900">{strategy.label}</p>
      {d?.scale_warning ? (
        <p className="mt-1 font-medium text-rose-800">
          Attenzione scala — {(d.warnings ?? []).join(', ')}
        </p>
      ) : null}
      <ul className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
        <li>MAE: {fmtNum(pm?.mae ?? strategy.metrics.mae, 3)}</li>
        <li>RMSE: {fmtNum(pm?.rmse ?? strategy.metrics.rmse, 3)}</li>
        <li>Bias: {fmtNum(pm?.bias ?? strategy.metrics.bias, 3)}</li>
        <li>Median abs error: {fmtNum(pm?.median_abs_error, 3)}</li>
        <li>Error std: {fmtNum(pm?.error_std, 3)}</li>
        <li>OK / failed: {pm?.predictions_ok ?? '—'} / {pm?.predictions_failed ?? '—'}</li>
        <li>Within 0.5: {fmtPct(pm?.within_0_5_pct)}</li>
        <li>Within 1.0: {fmtPct(pm?.within_1_0_pct)}</li>
        <li>Within 1.5: {fmtPct(pm?.within_1_5_pct)}</li>
        <li>Within 2.0: {fmtPct(pm?.within_2_0_pct)}</li>
      </ul>
    </div>
  )
}

function CoveragePanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const pm = strategy.predictive_metrics
  const cov = strategy.coverage_metrics
  const warning = cov?.coverage_bias_warning ?? pm?.coverage_bias_warning
  const samples = (strategy.coverage_samples ?? strategy.rows_sample ?? []).slice(0, 25)
  return (
    <div className="space-y-2 text-xs text-slate-700">
      <div className="rounded border border-slate-200 bg-white p-3">
        <p className="font-medium text-slate-900">Regola coverage WIN</p>
        <p className="mt-1">
          WIN se <strong>actual_total_sot &gt; predicted_total_sot</strong>; altrimenti LOSS.
        </p>
        <p className="mt-2">
          W/L: {pm?.coverage_win_count ?? cov?.coverage_win_count ?? 0} /{' '}
          {pm?.coverage_loss_count ?? cov?.coverage_loss_count ?? 0} — Rate:{' '}
          {fmtPct(pm?.coverage_win_rate ?? cov?.coverage_win_rate)}
        </p>
        {warning ? <p className="mt-2 font-medium text-amber-800">{warning}</p> : null}
        <p className="mt-2 text-slate-500">
          Una coverage alta con bias molto negativo può indicare sottostima e non vera precisione.
        </p>
      </div>
      <div className="overflow-x-auto rounded border border-slate-200 bg-white">
        <table className="min-w-full text-left text-[10px]">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-2 py-1">Match</th>
              <th className="px-2 py-1">Pred</th>
              <th className="px-2 py-1">Actual</th>
              <th className="px-2 py-1">Diff</th>
              <th className="px-2 py-1">Esito</th>
            </tr>
          </thead>
          <tbody>
            {samples.map((r) => {
              const row = r as Record<string, unknown>
              const pred = row.predicted_total_sot as number | undefined
              const act = row.actual_total_sot as number | undefined
              const diff = pred != null && act != null ? act - pred : null
              return (
                <tr key={String(row.fixture_id)} className="border-t border-slate-100">
                  <td className="px-2 py-1">{String(row.match ?? '')}</td>
                  <td className="px-2 py-1">{fmtNum(pred, 1)}</td>
                  <td className="px-2 py-1">{act ?? '—'}</td>
                  <td className="px-2 py-1">{diff != null ? fmtNum(diff, 1) : '—'}</td>
                  <td className="px-2 py-1">
                    {row.coverage_outcome === 'win' ? (
                      <span className="text-emerald-700">WIN</span>
                    ) : (
                      <span className="text-slate-600">LOSS</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function WorstErrorsPanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const ed = strategy.error_distribution
  return (
    <div className="grid gap-3 sm:grid-cols-2 text-xs text-slate-700">
      <ErrorList title="Worst underestimations (pred troppo basso)" items={ed?.worst_underestimations} />
      <ErrorList title="Worst overestimations (pred troppo alto)" items={ed?.worst_overestimations} />
    </div>
  )
}

function ErrorList({
  title,
  items,
}: {
  title: string
  items?: Array<{
    match?: string
    predicted_total_sot?: number
    actual_total_sot?: number
    error?: number
    possible_factors?: string[]
  }>
}) {
  return (
    <div className="rounded border border-slate-200 bg-white p-3">
      <p className="font-medium text-slate-900">{title}</p>
      <ul className="mt-2 space-y-2">
        {(items ?? []).map((e, i) => (
          <li key={i} className="border-b border-slate-100 pb-2 last:border-0">
            <p className="font-medium">{e.match}</p>
            <p>
              Pred {e.predicted_total_sot} · Actual {e.actual_total_sot} · Errore{' '}
              {fmtNum(e.error, 2)}
            </p>
            {(e.possible_factors ?? []).length > 0 ? (
              <p className="text-[10px] text-slate-500">{e.possible_factors?.join('; ')}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function WalkForwardPanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const wf = strategy.walk_forward_metrics
  return (
    <div className="space-y-2 text-xs text-slate-700">
      {Object.entries(wf).map(([k, v]) => (
        <div key={k} className="rounded border border-slate-200 bg-white p-3">
          <p className="font-medium">{k}</p>
          <p>Test giornate {v.test_rounds}</p>
          <p>Fixture test: {v.test_fixture_count}</p>
          <p>MAE test: {fmtNum(v.test_predictive?.mae, 3)}</p>
          <p>RMSE test: {fmtNum(v.test_predictive?.rmse, 3)}</p>
          <p>Bias test: {fmtNum(v.test_predictive?.bias, 3)}</p>
          <p>Within ±1.5 test: {fmtPct(v.test_predictive?.within_1_5_pct)}</p>
          <p>Coverage win test: {fmtPct(v.test_predictive?.coverage_win_rate)}</p>
        </div>
      ))}
    </div>
  )
}

function WeightsPanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const w = strategy.weights
  const basePct = w.base_weights_pct ?? w.base_weights ?? {}
  const ctxPct = w.context_weights_pct ?? w.context_weights ?? {}
  return (
    <div className="grid gap-3 sm:grid-cols-2 text-xs text-slate-700">
      <div className="rounded border border-slate-200 bg-white p-3">
        <p className="font-medium text-slate-900">Componenti base SOT (%)</p>
        <ul className="mt-2 space-y-0.5">
          {Object.entries(basePct).map(([k, v]) => (
            <li key={k} className="flex justify-between">
              <span>{k}</span>
              <span>{typeof v === 'number' && v < 2 ? `${(v * 100).toFixed(0)}%` : `${v}%`}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="rounded border border-slate-200 bg-white p-3">
        <p className="font-medium text-slate-900">Correttivi macro contesto (%)</p>
        <ul className="mt-2 space-y-0.5">
          {Object.entries(ctxPct).map(([k, v]) => (
            <li key={k} className="flex justify-between">
              <span>{k}</span>
              <span>{typeof v === 'number' && v < 2 ? `${(v * 100).toFixed(0)}%` : `${v}%`}</span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-slate-500">
          Cap context: {w.context_cap_min} – {w.context_cap_max} · Blend lega:{' '}
          {((w.total_league_blend ?? 0.4) * 100).toFixed(0)}%
          {w.uses_dynamic_bias ? ' · Bias dinamico: sì' : ''}
        </p>
      </div>
    </div>
  )
}

function AuditPanel({ audit }: { audit: V31CalibrationSimulator['audit'] }) {
  return (
    <div className="rounded border border-emerald-200 bg-emerald-50/60 p-3 text-xs text-emerald-900">
      <p className="text-sm font-semibold">Anti-leakage: {audit.anti_leakage ? 'OK' : 'FAILED'}</p>
      <p>Legacy predictions come feature: {audit.legacy_predictions_used_as_features ? 'sì' : 'no'}</p>
      <p>Target usato come input: {audit.target_used_as_input === false ? 'no' : 'sì'}</p>
      <p>Target solo per metriche: {audit.target_used_for_metrics_only ? 'sì' : 'no'}</p>
      <p>Comparisons solo audit: {audit.comparisons_used_for_audit_only ? 'sì' : 'no'}</p>
      <p>Campi vietati usati: {(audit.forbidden_fields_used ?? []).length}</p>
    </div>
  )
}
