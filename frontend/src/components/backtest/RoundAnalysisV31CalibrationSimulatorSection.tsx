import { useCallback, useState } from 'react'
import {
  getV31CalibrationSimulator,
  getV31CalibrationSimulatorReport,
  type V31CalibrationSimulator,
  type V31CalibrationSimulatorStrategy,
  type V31StrategyStatus,
  type V31WorstErrorRow,
} from '../../lib/api'

const TABS = [
  { id: 'strategies', label: 'Strategie' },
  { id: 'variance', label: 'Varianza modello' },
  { id: 'accuracy', label: 'Accuratezza' },
  { id: 'coverage', label: 'Coverage WIN' },
  { id: 'buckets', label: 'Bucket SOT' },
  { id: 'errors', label: 'Errori peggiori' },
  { id: 'walkforward', label: 'Walk-forward' },
  { id: 'weights', label: 'Pesi e variabili' },
  { id: 'audit', label: 'Audit anti-leakage' },
] as const

type TabId = (typeof TABS)[number]['id']

type StatusFilter = V31StrategyStatus | 'all'

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: 'active', label: 'Active' },
  { id: 'diagnostic', label: 'Diagnostic' },
  { id: 'archived', label: 'Archived' },
  { id: 'all', label: 'Tutte' },
]

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
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('active')
  const [errorsStrategyKey, setErrorsStrategyKey] = useState<string | null>(null)

  const run = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    setError(null)
    try {
      const res = await getV31CalibrationSimulator(competitionId, seasonYear, {
        strategy: 'all',
        strategyStatus: statusFilter === 'all' ? 'all' : statusFilter,
      })
      setData(res)
      const rec = res.best_by.recommended_strategy ?? res.strategies[0]?.key ?? null
      setSelectedKey(rec)
      setErrorsStrategyKey(rec)
    } catch (e) {
      setData(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [competitionId, seasonYear, statusFilter])

  const downloadBlob = (payload: unknown, name: string) => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadReportSummary = useCallback(async () => {
    if (competitionId == null) return
    setExporting(true)
    try {
      const payload = await getV31CalibrationSimulatorReport(competitionId, seasonYear, {
        strategy: 'all',
        strategyStatus: 'active',
        detail: 'summary',
      })
      downloadBlob(
        payload,
        `v31-predictive-simulator-summary-${competitionId}-${seasonYear}.json`,
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setExporting(false)
    }
  }, [competitionId, seasonYear])

  const downloadReportFull = useCallback(async () => {
    if (competitionId == null) return
    setExporting(true)
    try {
      const payload = await getV31CalibrationSimulatorReport(competitionId, seasonYear, {
        strategy: 'all',
        strategyStatus: 'all',
        detail: 'full',
      })
      downloadBlob(payload, `v31-predictive-simulator-full-${competitionId}-${seasonYear}.json`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setExporting(false)
    }
  }, [competitionId, seasonYear])

  const downloadReportSelected = useCallback(async () => {
    if (competitionId == null || !selectedKey) return
    setExporting(true)
    try {
      const payload = await getV31CalibrationSimulatorReport(competitionId, seasonYear, {
        strategy: selectedKey,
        strategyStatus: 'all',
        detail: 'full',
      })
      downloadBlob(
        payload,
        `v31-predictive-simulator-${selectedKey}-${competitionId}-${seasonYear}.json`,
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setExporting(false)
    }
  }, [competitionId, seasonYear, selectedKey])

  if (competitionId == null) return null

  const best = data?.best_by
  const visibleStrategies =
    data?.strategies.filter(
      (s) => statusFilter === 'all' || (s.strategy_status ?? 'active') === statusFilter,
    ) ?? []
  const selected =
    visibleStrategies.find((s) => s.key === selectedKey) ??
    data?.strategies.find((s) => s.key === selectedKey) ??
    visibleStrategies[0] ??
    data?.strategies[0]
  const recLabel =
    data?.summary.recommendation_note ??
    (best?.recommended_strategy
      ? data?.strategies.find((s) => s.key === best.recommended_strategy)?.label
      : null)

  const interp = data?.summary.model_interpretation
  const labelFor = (key?: string | null) =>
    key ? data?.strategies.find((s) => s.key === key)?.label ?? key : '—'

  const discouraged = data?.strategies.find(
    (s) =>
      s.key === 'v31_big_vs_weak_push' &&
      (s.strategy_warnings ?? []).some((w) => w.includes('Bias eccessivo')),
  )

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
            onClick={() => void downloadReportSummary()}
          >
            {exporting ? 'Export…' : 'Scarica report summary'}
          </button>
          <button
            type="button"
            disabled={exporting || !data}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => void downloadReportFull()}
          >
            Report completo
          </button>
          <button
            type="button"
            disabled={exporting || !data || !selectedKey}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => void downloadReportSelected()}
          >
            Report strategia
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
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/80 p-3 text-xs lg:col-span-2">
              <p className="font-medium text-emerald-800">Interpretazione modelli</p>
              <ul className="mt-2 space-y-1 text-emerald-900">
                <li>
                  Miglior numerico (MAE):{' '}
                  <strong>{labelFor(interp?.best_numeric_model ?? best?.best_numeric_model?.strategy)}</strong>
                </li>
                <li>
                  Miglior dinamico:{' '}
                  <strong>{labelFor(interp?.best_dynamic_model ?? best?.best_dynamic_model?.strategy)}</strong>
                </li>
                <li>
                  Compromesso consigliato:{' '}
                  <strong>{labelFor(interp?.best_compromise_model ?? best?.best_compromise_model?.strategy)}</strong>
                </li>
              </ul>
              <p className="mt-2 text-emerald-800">
                Al momento la migliore per MAE è v31_bias_corrected, ma non è ancora una v3.1 definitiva
                perché è troppo piatta.
              </p>
              {discouraged ? (
                <p className="mt-1 text-amber-800">
                  Modello sconsigliato: {discouraged.label} (bias eccessivo).
                </p>
              ) : null}
              {recLabel ? (
                <p className="mt-2 text-sm font-semibold text-emerald-900">{recLabel}</p>
              ) : null}
              {best?.compromise_score?.value != null ? (
                <p className="text-emerald-700">
                  Compromise score {fmtNum(best.compromise_score.value, 1)}
                </p>
              ) : null}
              {data.summary.recommendation_tradeoff ? (
                <p className="mt-2 text-emerald-900">{data.summary.recommendation_tradeoff}</p>
              ) : null}
              {(() => {
                const hybrid = data.strategies.find((s) => s.key === 'v31_bias_dynamic_high_guard')
                const hw = hybrid?.hybrid_debug?.hybrid_warnings ?? hybrid?.strategy_warnings ?? []
                const hybridWarns = hw.filter(
                  (w) =>
                    w.includes('V31_HYBRID') ||
                    w.includes('ibrida') ||
                    w === 'Modello troppo piatto',
                )
                return hybridWarns.length ? (
                  <ul className="mt-1 list-inside list-disc text-rose-800">
                    {hybridWarns.map((w) => (
                      <li key={w}>
                        {w === 'V31_HYBRID_IDENTICAL_TO_BASELINE'
                          ? 'La strategia ibrida non sta modificando la baseline.'
                          : w}
                      </li>
                    ))}
                  </ul>
                ) : null
              })()}
            </div>
          </div>

          <p className="text-[10px] text-slate-500">
            Fixture: {data.summary.fixtures_count} · Strategie: {data.summary.strategies_run} · Fase:{' '}
            {data.summary.phase ?? 'predictive_numeric'}
            {data.feature_availability?.avg_total_shots_for ? (
              <>
                {' '}
                · Shots ok: {data.feature_availability.avg_total_shots_for.available_count}/
                {data.feature_availability.avg_total_shots_for.fixtures_sides_total}
              </>
            ) : null}
          </p>

          {selected ? <VarianceSummaryCard strategy={selected} /> : null}

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

          <div className="flex flex-wrap gap-1">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                className={`rounded px-2 py-1 text-[10px] font-medium ${
                  statusFilter === f.id
                    ? 'bg-slate-800 text-white'
                    : 'bg-white text-slate-600 ring-1 ring-slate-200'
                }`}
                onClick={() => setStatusFilter(f.id)}
              >
                {f.label}
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
                    <th className="px-2 py-2">Pred std</th>
                    <th className="px-2 py-2">Compress.</th>
                    <th className="px-2 py-2">High rec.</th>
                    <th className="px-2 py-2">Pred&gt;9</th>
                    <th className="px-2 py-2">Act&gt;9</th>
                    <th className="px-2 py-2">Coverage W/L</th>
                    <th className="px-2 py-2">Coverage %</th>
                    <th className="px-2 py-2">Score</th>
                    <th className="px-2 py-2">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleStrategies.map((s) => (
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

          {activeTab === 'variance' && data ? <VarianceTable strategies={data.strategies} /> : null}
          {activeTab === 'accuracy' && selected ? <AccuracyPanel strategy={selected} /> : null}
          {activeTab === 'buckets' && selected ? <BucketsPanel strategy={selected} /> : null}
          {activeTab === 'coverage' && selected ? <CoveragePanel strategy={selected} /> : null}
          {activeTab === 'errors' && data ? (
            <WorstErrorsPanel
              strategies={visibleStrategies.length ? visibleStrategies : data.strategies}
              strategyKey={errorsStrategyKey}
              onStrategyKeyChange={setErrorsStrategyKey}
            />
          ) : null}
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
  const dist = s.prediction_distribution ?? s.prediction_diagnostics?.prediction_distribution
  const bm = s.bucket_metrics
  const covW = m.coverage_win_count ?? pm?.coverage_win_count ?? 0
  const covL = m.coverage_loss_count ?? pm?.coverage_loss_count ?? 0
  return (
    <tr
      className={`cursor-pointer border-t border-slate-100 ${selected ? 'bg-violet-50/50' : 'hover:bg-slate-50'}`}
      onClick={onSelect}
    >
      <td className="px-2 py-2 font-medium text-slate-800">
        {s.label}
        {s.strategy_status ? (
          <span className="ml-1 rounded bg-slate-100 px-1 py-0.5 text-[9px] text-slate-600">
            {s.strategy_status}
          </span>
        ) : null}
      </td>
      <td className="px-2 py-2">{fmtNum(m.predicted_avg ?? m.predicted_total_avg, 2)}</td>
      <td className="px-2 py-2">{fmtNum(m.actual_avg ?? m.actual_total_avg, 2)}</td>
      <td className="px-2 py-2">{fmtNum(m.mae, 3)}</td>
      <td className="px-2 py-2">{fmtNum(m.rmse, 3)}</td>
      <td className="px-2 py-2">{fmtNum(m.bias, 3)}</td>
      <td className="px-2 py-2">{fmtPct(m.within_1_0_pct ?? pm?.within_1_0_pct)}</td>
      <td className="px-2 py-2">{fmtPct(m.within_1_5_pct ?? pm?.within_1_5_pct)}</td>
      <td className="px-2 py-2">{fmtNum(m.predicted_std ?? dist?.predicted_std, 2)}</td>
      <td className="px-2 py-2">{fmtNum(m.compression_ratio ?? dist?.compression_ratio, 2)}</td>
      <td className="px-2 py-2">{fmtPct(m.high_total_recall ?? bm?.high_total_recall)}</td>
      <td className="px-2 py-2">{m.predicted_high_count_over_9 ?? dist?.predicted_high_count_over_9 ?? '—'}</td>
      <td className="px-2 py-2">{m.actual_high_count_over_9 ?? dist?.actual_high_count_over_9 ?? '—'}</td>
      <td className="px-2 py-2">
        {covW}/{covL}
      </td>
      <td className="px-2 py-2">{fmtPct(m.coverage_win_rate ?? pm?.coverage_win_rate)}</td>
      <td className="px-2 py-2">{fmtNum(s.dynamic_score ?? s.balanced_prediction_score, 1)}</td>
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

function WorstErrorsPanel({
  strategies,
  strategyKey,
  onStrategyKeyChange,
}: {
  strategies: V31CalibrationSimulatorStrategy[]
  strategyKey: string | null
  onStrategyKeyChange: (k: string) => void
}) {
  const strategy = strategies.find((s) => s.key === strategyKey) ?? strategies[0]
  const ed = strategy?.error_distribution
  return (
    <div className="space-y-2 text-xs text-slate-700">
      <label className="flex items-center gap-2">
        <span className="font-medium">Strategia</span>
        <select
          className="rounded border border-slate-200 px-2 py-1 text-xs"
          value={strategy?.key ?? ''}
          onChange={(e) => onStrategyKeyChange(e.target.value)}
        >
          {strategies.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <ErrorList title="Worst underestimations (pred troppo basso)" items={ed?.worst_underestimations} />
        <ErrorList title="Worst overestimations (pred troppo alto)" items={ed?.worst_overestimations} />
      </div>
    </div>
  )
}

function ErrorList({
  title,
  items,
}: {
  title: string
  items?: V31WorstErrorRow[]
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
            <p className="text-[10px] text-slate-500">
              Bucket pred/real: {e.predicted_bucket ?? '—'} / {e.actual_bucket ?? '—'}
            </p>
            <p className="text-[10px] text-slate-500">
              Boost: {fmtNum(e.boost_applied as number | undefined, 2)} · Signal:{' '}
              {fmtNum(e.high_total_signal as number | undefined, 2)}
            </p>
            <p className="text-[10px] text-violet-800">
              {e.probable_reason || 'Motivo non disponibile'}
            </p>
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

function VarianceSummaryCard({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const dist = strategy.prediction_distribution ?? strategy.prediction_diagnostics?.prediction_distribution
  const flat = dist?.model_too_flat ?? strategy.metrics?.model_too_flat
  return (
    <div className="rounded border border-slate-200 bg-white p-3 text-xs text-slate-700">
      <p className="font-medium text-slate-900">Varianza modello — {strategy.label}</p>
      <div className="mt-2 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <span>Pred std: {fmtNum(dist?.predicted_std, 2)}</span>
        <span>Actual std: {fmtNum(dist?.actual_std, 2)}</span>
        <span>Compression: {fmtNum(dist?.compression_ratio, 2)}</span>
        <span>Pred &gt; 9: {dist?.predicted_high_count_over_9 ?? '—'}</span>
        <span>Actual &gt; 9: {dist?.actual_high_count_over_9 ?? '—'}</span>
        <span>
          {flat ? (
            <span className="font-medium text-rose-700">Modello troppo piatto</span>
          ) : (
            <span className="text-emerald-700">Varianza OK</span>
          )}
        </span>
      </div>
    </div>
  )
}

function VarianceTable({ strategies }: { strategies: V31CalibrationSimulatorStrategy[] }) {
  return (
    <div className="overflow-x-auto rounded border border-slate-200 bg-white">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            <th className="px-2 py-2">Strategia</th>
            <th className="px-2 py-2">Pred std</th>
            <th className="px-2 py-2">Actual std</th>
            <th className="px-2 py-2">Compression</th>
            <th className="px-2 py-2">Pred&gt;9</th>
            <th className="px-2 py-2">Actual&gt;9</th>
            <th className="px-2 py-2">Piatto?</th>
          </tr>
        </thead>
        <tbody>
          {strategies.map((s) => {
            const d = s.prediction_distribution ?? s.prediction_diagnostics?.prediction_distribution
            return (
              <tr key={s.key} className="border-t border-slate-100">
                <td className="px-2 py-2 font-medium">{s.label}</td>
                <td className="px-2 py-2">{fmtNum(d?.predicted_std, 2)}</td>
                <td className="px-2 py-2">{fmtNum(d?.actual_std, 2)}</td>
                <td className="px-2 py-2">{fmtNum(d?.compression_ratio, 2)}</td>
                <td className="px-2 py-2">{d?.predicted_high_count_over_9 ?? '—'}</td>
                <td className="px-2 py-2">{d?.actual_high_count_over_9 ?? '—'}</td>
                <td className="px-2 py-2">{d?.model_too_flat ? 'Sì' : 'No'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function BucketsPanel({ strategy }: { strategy: V31CalibrationSimulatorStrategy }) {
  const bm = strategy.bucket_metrics
  const cm = bm?.confusion_matrix as Record<string, Record<string, number>> | undefined
  return (
    <div className="space-y-3 text-xs text-slate-700">
      <div className="rounded border border-slate-200 bg-white p-3">
        <p className="font-medium">{strategy.label}</p>
        <ul className="mt-2 grid gap-1 sm:grid-cols-2">
          <li>Bucket accuracy: {fmtPct(bm?.bucket_accuracy)}</li>
          <li>High recall: {fmtPct(bm?.high_total_recall)}</li>
          <li>High precision: {fmtPct(bm?.high_total_precision)}</li>
          <li>Low recall: {fmtPct(bm?.low_total_recall)}</li>
          <li>
            High actual / pred: {bm?.high_actual_count ?? '—'} / {bm?.high_predicted_count ?? '—'}
          </li>
        </ul>
      </div>
      {cm ? (
        <div className="overflow-x-auto rounded border border-slate-200 bg-white p-3">
          <p className="mb-2 font-medium">Confusion matrix (pred → actual)</p>
          <table className="text-[10px]">
            <thead>
              <tr>
                <th className="px-1">pred \ actual</th>
                {['low_total', 'normal_total', 'high_total', 'very_high_total'].map((b) => (
                  <th key={b} className="px-1">
                    {b.replace('_total', '')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(cm).map(([pred, row]) => (
                <tr key={pred}>
                  <td className="px-1 font-medium">{pred.replace('_total', '')}</td>
                  {['low_total', 'normal_total', 'high_total', 'very_high_total'].map((ab) => (
                    <td key={ab} className="px-1 text-center">
                      {row[ab] ?? 0}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
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
