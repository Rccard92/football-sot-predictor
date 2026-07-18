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

function shortHash(h: unknown): string {
  const s = String(h || '')
  if (!s) return '—'
  return s.length > 10 ? `${s.slice(0, 10)}…` : s
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
  const oofId = data?.oof_evaluation_identity as Record<string, unknown> | undefined
  const temporal = data?.temporal_span as Record<string, unknown> | undefined
  const fair = data?.fair_book_probability_audit as Record<string, unknown> | undefined
  const dc = (fair?.double_chance || {}) as Record<string, unknown>
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
  const ecoPaired = (economic.paired_comparisons || {}) as Record<string, Record<string, unknown>>
  const sourceRows =
    (fair?.all_observed_source_counts as Array<Record<string, unknown>>) ||
    (fair?.sources as Array<Record<string, unknown>>) ||
    []
  const reasonCodes = (readiness?.readiness_reason_codes as string[]) || []
  const evaluatedMk = (fair?.markets_residual_evaluated as string[]) || []
  const expectedMk = (fair?.expected_markets as string[]) || markets.map((m) => String(m.market))

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
                className="ml-1 rounded border border-slate-300 px-2 py-1"
                value={dateFrom}
                onChange={(e) => onDateFrom(e.target.value)}
              />
            </label>
            <label className="text-slate-600">
              A
              <input
                type="date"
                className="ml-1 rounded border border-slate-300 px-2 py-1"
                value={dateTo}
                onChange={(e) => onDateTo(e.target.value)}
              />
            </label>
            <label className="text-slate-600">
              Selection
              <input
                className="ml-1 rounded border border-slate-300 px-2 py-1"
                value={selection}
                onChange={(e) => onSelection(e.target.value)}
                placeholder="opzionale"
              />
            </label>
            <label className="text-slate-600">
              Bootstrap
              <input
                type="number"
                className="ml-1 w-24 rounded border border-slate-300 px-2 py-1"
                value={bootstrapIterations}
                onChange={(e) => onBootstrap(Number(e.target.value) || 200)}
              />
            </label>
          </div>
          <button
            type="button"
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            onClick={onRefresh}
            disabled={loading || jobRunning}
          >
            {loading || jobRunning ? 'Calcolo…' : 'Avvia ricerca residuale'}
          </button>
        </div>
        {jobRunning ? (
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
                <dt className="text-slate-500">Source settled / residual</dt>
                <dd className="font-medium">
                  {String(data.source_settled_rows ?? '—')} /{' '}
                  {String(identity?.residual_rows ?? readiness?.residual_core_rows ?? '—')}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">OOF evaluable / fixture</dt>
                <dd className="font-medium">
                  {String(oofId?.oof_evaluable_rows ?? '—')} /{' '}
                  {String(identity?.fixtures ?? readiness?.unique_fixtures ?? '—')}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Mercati valutati / attesi</dt>
                <dd className="font-medium">
                  {evaluatedMk.length} / {expectedMk.length || 10}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Temporal span (gg)</dt>
                <dd className="font-medium">
                  {String(temporal?.temporal_span_days ?? readiness?.temporal_span_days ?? '—')}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Calendar months</dt>
                <dd className="font-medium">
                  {String(temporal?.unique_calendar_months ?? readiness?.unique_calendar_months ?? '—')}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Limited temporal</dt>
                <dd className="font-medium">
                  {(temporal?.limited_temporal_span ?? readiness?.limited_temporal_span) === true
                    ? 'sì'
                    : 'no'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Readiness</dt>
                <dd className="font-medium">{String(readiness?.recommended_next_step || '—')}</dd>
              </div>
              <div className="sm:col-span-2 lg:col-span-4">
                <dt className="text-slate-500">Reason codes</dt>
                <dd className="font-medium text-xs text-slate-700">
                  {reasonCodes.length ? reasonCodes.join(', ') : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Elapsed</dt>
                <dd className="font-medium">{formatElapsedMs(elapsedMs)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Bootstrap</dt>
                <dd className="font-medium">
                  {data.filters?.bootstrap_iterations ?? bootstrapIterations}
                </dd>
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

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Fair Book — sorgenti</h3>
            <table className="mt-3 w-full min-w-[800px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Source</th>
                  <th className="py-1 pr-2">Observed</th>
                  <th className="py-1 pr-2">Settled</th>
                  <th className="py-1 pr-2">Verified settled</th>
                  <th className="py-1 pr-2">Residual</th>
                  <th className="py-1">Coverage settled</th>
                </tr>
              </thead>
              <tbody>
                {sourceRows.map((s) => (
                  <tr key={String(s.source)} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2 text-xs">{String(s.source)}</td>
                    <td className="py-1.5 pr-2">{String(s.observed_rows ?? s.rows ?? '—')}</td>
                    <td className="py-1.5 pr-2">{String(s.settled_rows ?? '—')}</td>
                    <td className="py-1.5 pr-2">
                      {String(s.verified_settled_rows ?? s.verified_rows ?? '—')}
                    </td>
                    <td className="py-1.5 pr-2">{String(s.residual_rows ?? '—')}</td>
                    <td className="py-1.5">{fmt(s.verified_coverage_settled as number)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-4 rounded-lg border border-slate-100 bg-slate-50 p-3 text-sm">
              <h4 className="font-medium text-slate-800">Doppia Chance</h4>
              <dl className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <dt className="text-slate-500 text-xs">Input / linkable</dt>
                  <dd>
                    {String(dc.dc_input_rows ?? '—')} / {String(dc.dc_cross_market_linkable_rows ?? '—')}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 text-xs">Derived / residual</dt>
                  <dd>
                    {String(dc.dc_derived_verified_rows ?? '—')} / {String(dc.dc_residual_rows ?? '—')}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 text-xs">Missing 1X2 / snap / BM / provider</dt>
                  <dd className="text-xs">
                    {String(dc.dc_missing_1x2_rows ?? 0)} / {String(dc.dc_snapshot_mismatch_rows ?? 0)} /{' '}
                    {String(dc.dc_bookmaker_mismatch_rows ?? 0)} /{' '}
                    {String(dc.dc_provider_mismatch_rows ?? 0)}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 text-xs">Linkage status</dt>
                  <dd>{String(dc.linkage_status ?? '—')}</dd>
                </div>
              </dl>
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Specifiche (binary OOF)</h3>
            <table className="mt-3 w-full min-w-[1100px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Spec</th>
                  <th className="py-1 pr-2">AUC</th>
                  <th className="py-1 pr-2">Brier</th>
                  <th className="py-1 pr-2">LogLoss</th>
                  <th className="py-1 pr-2">n source</th>
                  <th className="py-1 pr-2">n OOF</th>
                  <th className="py-1 pr-2">OOF coverage</th>
                  <th className="py-1">Eval hash</th>
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
                      <td className="py-1.5 pr-2">{String(row.n_source ?? '—')}</td>
                      <td className="py-1.5 pr-2">{String(row.n_oof ?? '—')}</td>
                      <td className="py-1.5 pr-2">{fmt(row.oof_coverage as number)}</td>
                      <td className="py-1.5 text-xs">{shortHash(row.evaluation_row_key_hash)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Paired (decisivo vs GAP_ONLY)</h3>
            <table className="mt-3 w-full min-w-[900px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Confronto</th>
                  <th className="py-1 pr-2">ΔAUC</th>
                  <th className="py-1 pr-2">ΔBrier↑</th>
                  <th className="py-1 pr-2">ΔLL↑</th>
                  <th className="py-1 pr-2">paired n</th>
                  <th className="py-1">hash</th>
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
                      <td className="py-1.5 pr-2">{fmt(row.delta_log_loss_improvement as number)}</td>
                      <td className="py-1.5 pr-2">{String(row.paired_n ?? row.n_paired ?? '—')}</td>
                      <td className="py-1.5 text-xs">{shortHash(row.paired_row_key_hash)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">
              Economica — solo positive-value cohort (OOF)
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              Source positive: {String(economic.source_positive_rows ?? economic.positive_value_rows ?? '—')} ·
              OOF positive: {String(economic.oof_positive_rows ?? '—')} · coverage{' '}
              {fmt(economic.oof_coverage as number)} · stake 1
            </p>
            <table className="mt-3 w-full min-w-[900px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Spec</th>
                  <th className="py-1 pr-2">OOF rows</th>
                  <th className="py-1 pr-2">Coverage</th>
                  <th className="py-1 pr-2">ROI top 10%</th>
                  <th className="py-1 pr-2">ROI top 20%</th>
                  <th className="py-1">ROI top quintile</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(ecoBySpec).map(([name, m]) => (
                  <tr key={name} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2 text-xs">{name}</td>
                    <td className="py-1.5 pr-2">{String(m.oof_positive_rows ?? '—')}</td>
                    <td className="py-1.5 pr-2">{fmt(m.oof_coverage as number)}</td>
                    <td className="py-1.5 pr-2">{fmt(m.roi_top_10pct as number)}</td>
                    <td className="py-1.5 pr-2">{fmt(m.roi_top_20pct as number)}</td>
                    <td className="py-1.5">{fmt(m.roi_top_quintile as number)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {Object.keys(ecoPaired).length ? (
              <>
                <h4 className="mt-4 text-sm font-medium text-slate-800">Paired economica</h4>
                <table className="mt-2 w-full min-w-[900px] text-left text-sm">
                  <thead className="border-b border-slate-200 text-slate-500">
                    <tr>
                      <th className="py-1 pr-2">Confronto</th>
                      <th className="py-1 pr-2">paired</th>
                      <th className="py-1 pr-2">ΔROI 10%</th>
                      <th className="py-1 pr-2">ΔROI 20%</th>
                      <th className="py-1 pr-2">ΔROI Q</th>
                      <th className="py-1">CI 10%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(ecoPaired).map(([name, m]) => {
                      const ci = (m.ci_delta_roi_top_10pct || {}) as Record<string, unknown>
                      return (
                        <tr key={name} className="border-b border-slate-100">
                          <td className="py-1.5 pr-2 text-xs">{name}</td>
                          <td className="py-1.5 pr-2">{String(m.paired_rows ?? '—')}</td>
                          <td className="py-1.5 pr-2">{fmt(m.delta_roi_top_10pct as number)}</td>
                          <td className="py-1.5 pr-2">{fmt(m.delta_roi_top_20pct as number)}</td>
                          <td className="py-1.5 pr-2">{fmt(m.delta_roi_top_quintile as number)}</td>
                          <td className="py-1.5 text-xs">
                            [{fmt(ci.ci_low as number)}, {fmt(ci.ci_high as number)}]
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </>
            ) : null}
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
            <h3 className="text-sm font-semibold text-slate-900">Mercati (10 attesi) / Fold</h3>
            <table className="mt-3 w-full min-w-[600px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Mercato</th>
                  <th className="py-1 pr-2">Rows</th>
                  <th className="py-1 pr-2">Fixture</th>
                  <th className="py-1">Status</th>
                </tr>
              </thead>
              <tbody>
                {markets.map((m) => (
                  <tr key={String(m.market)} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2">{String(m.market)}</td>
                    <td className="py-1.5 pr-2">{String(m.rows ?? 0)}</td>
                    <td className="py-1.5 pr-2">{String(m.fixtures ?? 0)}</td>
                    <td className="py-1.5">{String(m.status ?? '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-slate-500">Fold temporali: {folds.length}</p>
          </section>
        </>
      ) : null}
    </div>
  )
}
