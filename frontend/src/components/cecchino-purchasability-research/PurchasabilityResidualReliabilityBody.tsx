import type {
  PurchasabilityResearchJobStatus,
  PurchasabilityResidualExportKind,
  PurchasabilityResidualFilters,
  PurchasabilityResidualReliabilityResponse,
} from '../../lib/cecchinoPurchasabilityResidualApi'
import {
  buildPurchasabilityResidualExportUrl,
  formatElapsedMs,
} from '../../lib/cecchinoPurchasabilityResidualApi'

type Props = {
  data: PurchasabilityResidualReliabilityResponse | null
  loading: boolean
  error: string | null
  detailWarning?: string | null
  job: PurchasabilityResearchJobStatus | null
  dateFrom: string
  dateTo: string
  selection: string
  bootstrapIterations: number
  onDateFrom: (v: string) => void
  onDateTo: (v: string) => void
  onSelection: (v: string) => void
  onBootstrap: (v: number) => void
  onRefresh: () => void
  filters: () => PurchasabilityResidualFilters
}

const EXPORTS: Array<[PurchasabilityResidualExportKind, string]> = [
  ['summary', 'Summary'],
  ['cohort', 'Cohort'],
  ['fair-book-audit', 'Fair Book'],
  ['feature-audit', 'Feature audit'],
  ['folds', 'Fold'],
  ['markets', 'Mercati'],
  ['binary-results', 'Binary'],
  ['residual-results', 'Residual'],
  ['paired', 'Paired'],
  ['economic', 'Economica'],
  ['decisions', 'Decisioni'],
  ['readiness', 'Readiness 2B'],
]

function fmt(n: number | null | undefined, digits = 3): string {
  if (n == null || Number.isNaN(n)) return '—'
  return Number(n).toFixed(digits)
}

export function PurchasabilityResidualReliabilityBody({
  data,
  loading,
  error,
  detailWarning,
  job,
  dateFrom,
  dateTo,
  selection,
  bootstrapIterations,
  onDateFrom,
  onDateTo,
  onSelection,
  onBootstrap,
  onRefresh,
  filters,
}: Props) {
  const readiness = data?.phase_2b_residual_readiness as Record<string, unknown> | undefined
  const identity = data?.cohort_identity as Record<string, unknown> | undefined
  const fair = data?.fair_book_probability_audit as Record<string, unknown> | undefined
  const jobRunning = job?.status === 'queued' || job?.status === 'running'
  const shortJobId = job?.job_id ? `${job.job_id.slice(0, 8)}…` : null
  const elapsedMs = data?.elapsed_ms?.total
  const binary = data?.binary_results || {}
  const paired = data?.paired_comparisons || {}
  const decisions = data?.feature_decisions || []
  const markets = data?.market_results || []
  const folds = data?.temporal_folds || []
  const economic = (data?.economic_diagnostics || {}) as Record<string, unknown>
  const ecoBySpec = (economic.by_specification || {}) as Record<string, Record<string, unknown>>

  return (
    <div className="space-y-4">
      <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        {data?.research_banner ||
          'Questa fase studia l’affidabilità del disaccordo tra Cecchino e Book. Non calcola ancora l’Indice di Acquistabilità e non influenza i Segnali.'}
      </p>

      {error ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>
      ) : null}
      {detailWarning ? (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {detailWarning}
        </p>
      ) : null}

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap gap-3 text-sm">
            <label className="text-slate-600">
              Da
              <input
                type="date"
                className="ml-2 rounded border border-slate-300 px-2 py-1"
                value={dateFrom}
                onChange={(e) => onDateFrom(e.target.value)}
              />
            </label>
            <label className="text-slate-600">
              A
              <input
                type="date"
                className="ml-2 rounded border border-slate-300 px-2 py-1"
                value={dateTo}
                onChange={(e) => onDateTo(e.target.value)}
              />
            </label>
            <label className="text-slate-600">
              Selezione
              <input
                className="ml-2 rounded border border-slate-300 px-2 py-1"
                placeholder="es. HOME"
                value={selection}
                onChange={(e) => onSelection(e.target.value)}
              />
            </label>
            <label className="text-slate-600">
              Bootstrap
              <select
                className="ml-2 rounded border border-slate-300 px-2 py-1"
                value={bootstrapIterations}
                onChange={(e) => onBootstrap(Number(e.target.value))}
                disabled={loading}
              >
                <option value={200}>200</option>
                <option value={500}>500</option>
              </select>
            </label>
          </div>
          <button
            type="button"
            disabled={loading}
            onClick={() => onRefresh()}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {loading ? 'Calcolo…' : 'Esegui residual research'}
          </button>
        </div>
        {loading || jobRunning ? (
          <div className="mt-3 space-y-1 text-sm text-slate-600">
            <p>Ricerca residuale in esecuzione sul backend.</p>
            <p className="text-xs text-slate-500">
              Job {shortJobId || '—'} · stato {job?.status || '…'} · fase{' '}
              {job?.current_stage || job?.progress_message || '…'} · mode residual · bootstrap{' '}
              {bootstrapIterations}
            </p>
          </div>
        ) : null}
      </div>

      {data ? (
        <>
          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-slate-900">Header</h3>
            <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="text-slate-500">Versione</dt>
                <dd className="font-medium">{data.version}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Dataset</dt>
                <dd className="font-medium">{data.dataset_version}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Residual rows / fixture</dt>
                <dd className="font-medium">
                  {String(identity?.residual_rows ?? readiness?.residual_core_rows ?? '—')} /{' '}
                  {String(identity?.fixtures ?? readiness?.unique_fixtures ?? '—')}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Readiness</dt>
                <dd className="font-medium">{String(readiness?.recommended_next_step || '—')}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Elapsed</dt>
                <dd className="font-medium">{formatElapsedMs(elapsedMs)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Limited temporal</dt>
                <dd className="font-medium">
                  {readiness?.limited_temporal_span === true ? 'sì' : 'no'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Bootstrap</dt>
                <dd className="font-medium">
                  {data.filters?.bootstrap_iterations ?? bootstrapIterations}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Source 2A</dt>
                <dd className="font-medium text-xs">{data.source_statistical_version || '—'}</dd>
              </div>
            </dl>
            <div className="mt-3 flex flex-wrap gap-2">
              {EXPORTS.map(([kind, label]) => (
                <a
                  key={kind}
                  className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                  href={buildPurchasabilityResidualExportUrl(kind, filters())}
                  target="_blank"
                  rel="noreferrer"
                >
                  {label}
                </a>
              ))}
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-slate-900">Fair Book</h3>
            <ul className="mt-2 space-y-1 text-sm text-slate-700">
              {((fair?.sources as Array<Record<string, unknown>>) || []).map((s) => (
                <li key={String(s.source)}>
                  {String(s.source)}: {String(s.rows)} righe (verified {String(s.verified_rows)})
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Specifiche (binary OOF)</h3>
            <table className="mt-3 w-full min-w-[900px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Spec</th>
                  <th className="py-1 pr-2">AUC</th>
                  <th className="py-1 pr-2">Brier</th>
                  <th className="py-1 pr-2">LogLoss</th>
                  <th className="py-1">n OOF</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(binary).map(([name, m]) => {
                  const row = m as Record<string, unknown>
                  return (
                    <tr key={name} className="border-b border-slate-100">
                      <td className="py-1.5 pr-2 font-medium">{name}</td>
                      <td className="py-1.5 pr-2">{fmt(row.auc as number)}</td>
                      <td className="py-1.5 pr-2">{fmt(row.brier as number)}</td>
                      <td className="py-1.5 pr-2">{fmt(row.log_loss as number)}</td>
                      <td className="py-1.5">{String(row.n_oof ?? '—')}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Paired (decisivo vs GAP_ONLY)</h3>
            <table className="mt-3 w-full min-w-[800px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Confronto</th>
                  <th className="py-1 pr-2">ΔAUC</th>
                  <th className="py-1 pr-2">ΔBrier↑</th>
                  <th className="py-1">ΔLL↑</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(paired).map(([name, m]) => {
                  const row = m as Record<string, unknown>
                  return (
                    <tr key={name} className="border-b border-slate-100">
                      <td className="py-1.5 pr-2 text-xs">{name}</td>
                      <td className="py-1.5 pr-2">{fmt(row.delta_auc as number)}</td>
                      <td className="py-1.5 pr-2">{fmt(row.delta_brier_improvement as number)}</td>
                      <td className="py-1.5">{fmt(row.delta_log_loss_improvement as number)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">
              Economica — solo positive-value cohort
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              Rows positive-value: {String(economic.positive_value_rows ?? '—')} · stake 1
            </p>
            <table className="mt-3 w-full min-w-[700px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Spec</th>
                  <th className="py-1 pr-2">ROI top 10%</th>
                  <th className="py-1 pr-2">ROI top 20%</th>
                  <th className="py-1">ROI top quintile</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(ecoBySpec).map(([name, m]) => (
                  <tr key={name} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2 text-xs">{name}</td>
                    <td className="py-1.5 pr-2">{fmt(m.roi_top_10pct as number)}</td>
                    <td className="py-1.5 pr-2">{fmt(m.roi_top_20pct as number)}</td>
                    <td className="py-1.5">{fmt(m.roi_top_quintile as number)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Feature decisions</h3>
            <table className="mt-3 w-full min-w-[700px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Feature</th>
                  <th className="py-1 pr-2">Role</th>
                  <th className="py-1 pr-2">Decision</th>
                  <th className="py-1">Reason</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((d) => (
                  <tr key={String(d.feature)} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2">{String(d.feature)}</td>
                    <td className="py-1.5 pr-2 text-xs">{String(d.role)}</td>
                    <td className="py-1.5 pr-2">{String(d.decision)}</td>
                    <td className="py-1.5 text-xs text-slate-600">{String(d.reason || '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Mercati / Fold</h3>
            <p className="mt-1 text-xs text-slate-500">
              Mercati con residual rows:{' '}
              {markets
                .filter((m) => Number(m.rows || 0) > 0)
                .map((m) => String(m.market))
                .join(', ') || '—'}
            </p>
            <p className="mt-1 text-xs text-slate-500">Fold temporali: {folds.length}</p>
          </section>
        </>
      ) : null}
    </div>
  )
}
