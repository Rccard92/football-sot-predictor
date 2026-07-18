import type {
  PurchasabilityResearchJobStatus,
  PurchasabilityStatExportKind,
  PurchasabilityStatFilters,
  PurchasabilityStatisticalResearchResponse,
} from '../../lib/cecchinoPurchasabilityStatisticalApi'
import {
  buildPurchasabilityStatExportUrl,
  formatElapsedMs,
} from '../../lib/cecchinoPurchasabilityStatisticalApi'

type Props = {
  data: PurchasabilityStatisticalResearchResponse | null
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
  filters: () => PurchasabilityStatFilters
}

const EXPORTS: Array<[PurchasabilityStatExportKind, string]> = [
  ['summary', 'Summary'],
  ['cohort_identity', 'Cohort'],
  ['temporal_folds', 'Fold'],
  ['market_results', 'Mercati'],
  ['univariate_evidence', 'Univariate'],
  ['candidate_comparison', 'Candidati'],
  ['marginal_contribution', 'Marginale'],
  ['feature_decisions', 'Decisioni'],
  ['rating_benchmark', 'Rating'],
  ['readiness', 'Readiness 2B'],
]

function fmt(n: number | null | undefined, digits = 3): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

export function PurchasabilityStatisticalResearchBody({
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
  const identity = data?.cohort_identity
  const readiness = data?.phase_2b_readiness
  const rating = data?.rating_benchmark
  const bookAssess = data?.book_baseline_assessment
  const decisionByConfig = new Map(
    (data?.feature_decisions || []).map((f) => [f.feature_name, f.decision]),
  )
  const candidates = (data?.candidate_specifications || []).filter(
    (c) => c.configuration !== 'BOOK_BASELINE' && !c.is_book_baseline_benchmark,
  )
  const bookBenchmark = (data?.candidate_specifications || []).find(
    (c) => c.configuration === 'BOOK_BASELINE' || c.is_book_baseline_benchmark,
  )
  const jobRunning = job?.status === 'queued' || job?.status === 'running'
  const shortJobId = job?.job_id ? `${job.job_id.slice(0, 8)}…` : null
  const elapsedMs = data?.elapsed_ms?.total

  return (
    <div className="space-y-4">
      <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        {data?.research_banner ||
          'Fase di ricerca statistica. Nessun Indice di Acquistabilità produttivo. Nessuna influenza sui Segnali Cecchino.'}
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
            {loading ? 'Calcolo…' : 'Esegui ricerca'}
          </button>
        </div>
        {loading || jobRunning ? (
          <div className="mt-3 space-y-1 text-sm text-slate-600">
            <p>Ricerca statistica in esecuzione sul backend.</p>
            <p className="text-xs text-slate-500">
              Job {shortJobId || '—'} · stato {job?.status || '…'} · fase{' '}
              {job?.current_stage || job?.progress_message || '…'} · elapsed{' '}
              {job?.elapsed_seconds != null ? `${job.elapsed_seconds}s` : '—'} · bootstrap{' '}
              {bootstrapIterations} · intervallo {dateFrom || '—'} → {dateTo || '—'}
            </p>
            <p className="text-xs text-slate-500">
              Puoi cambiare pagina: il calcolo continuerà sul backend. Tornando in questa sezione
              verrà recuperato lo stato del job. I job non sopravvivono a restart o nuovo deploy.
            </p>
            {data ? (
              <p className="text-xs font-medium text-amber-800">
                Nuovo calcolo in corso — risultati precedenti ancora visibili.
              </p>
            ) : null}
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
                <dt className="text-slate-500">Bootstrap richiesti</dt>
                <dd className="font-medium">
                  {data.filters?.bootstrap_iterations ?? bootstrapIterations}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Elapsed</dt>
                <dd className="font-medium" title={elapsedMs != null ? `${elapsedMs} ms` : undefined}>
                  {formatElapsedMs(elapsedMs)}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Stato</dt>
                <dd className="font-medium">{data.status}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Readiness 2B</dt>
                <dd className="font-medium">{readiness?.recommended_next_step || '—'}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Book dominance</dt>
                <dd className="font-medium">
                  {bookAssess?.dominance_status ||
                    readiness?.book_baseline_dominance ||
                    '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Rating decision</dt>
                <dd className="font-medium">{readiness?.rating_decision || rating?.conclusion || '—'}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Range</dt>
                <dd className="font-medium">
                  {identity?.date_min || '—'} → {identity?.date_max || '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Settled / fixture</dt>
                <dd className="font-medium">
                  {identity?.settled_rows ?? 0} / {identity?.unique_fixtures ?? 0}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Invariants</dt>
                <dd className="font-medium">
                  {readiness?.readiness_invariants_passed === true
                    ? 'ok'
                    : readiness?.readiness_invariants_passed === false
                      ? 'fail'
                      : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Paired unici</dt>
                <dd className="font-medium">
                  {data.paired_comparisons_unique ??
                    readiness?.paired_comparisons_unique ??
                    '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Duplicati rimossi</dt>
                <dd className="font-medium">
                  {data.paired_duplicates_removed ??
                    readiness?.paired_duplicates_removed ??
                    0}
                </dd>
              </div>
            </dl>
            {(readiness?.readiness_invariant_errors || []).length > 0 ? (
              <p className="mt-2 text-xs text-red-700">
                Errori invariant: {(readiness?.readiness_invariant_errors || []).join(', ')}
              </p>
            ) : null}
            {(data.limitations || []).length > 0 ? (
              <p className="mt-3 text-xs text-amber-800">
                Limitazioni: {(data.limitations || []).join(', ')}
              </p>
            ) : null}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-slate-900">Contatori indipendenza</h3>
            <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-5">
              <div>
                <dt className="text-slate-500">Positivi vs Book</dt>
                <dd className="font-medium">{readiness?.paired_positive_vs_book ?? 0}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Positivi vs Model</dt>
                <dd className="font-medium">{readiness?.paired_positive_vs_model ?? 0}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Positivi vs Rating</dt>
                <dd className="font-medium">{readiness?.paired_positive_vs_rating ?? 0}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Candidati indipendenti</dt>
                <dd className="font-medium">
                  {(readiness?.independent_candidate_specs || []).length}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Model enrichment</dt>
                <dd className="font-medium">
                  {(readiness?.model_enrichment_specs || []).length}
                </dd>
              </div>
            </dl>
            <p className="mt-3 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
              Un miglioramento rispetto al solo modello Cecchino non dimostra un vantaggio
              indipendente rispetto al mercato.
            </p>
          </section>

          {bookBenchmark ? (
            <section className="rounded-xl border border-slate-200 bg-white p-4">
              <h3 className="text-sm font-semibold text-slate-900">
                BOOK_BASELINE — benchmark di mercato
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                Non è un candidato all&apos;Acquistabilità: confronta le altre specifiche rispetto a
                questa baseline.
              </p>
              <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <dt className="text-slate-500">AUC</dt>
                  <dd className="font-medium">{fmt(bookBenchmark.auc_mean)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Brier</dt>
                  <dd className="font-medium">{fmt(bookBenchmark.brier_mean)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">ROI top10%</dt>
                  <dd className="font-medium">{fmt(bookBenchmark.roi_top_10pct_mean)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Dominance</dt>
                  <dd className="font-medium">{bookAssess?.dominance_status || '—'}</dd>
                </div>
              </dl>
            </section>
          ) : null}

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Candidati</h3>
            <p className="mt-1 text-xs text-slate-500">
              ROI coorte = full coverage (non discriminante tra modelli). Confrontare ROI top 10%/20%
              e Δ paired vs Book. Advantage/Edge contengono informazione Book.
            </p>
            <table className="mt-3 w-full min-w-[1200px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Config</th>
                  <th className="py-1 pr-2">AUC</th>
                  <th className="py-1 pr-2">Book info</th>
                  <th className="py-1 pr-2">ΔAUC vs Book</th>
                  <th className="py-1 pr-2">ΔBrier vs Book</th>
                  <th className="py-1 pr-2">ROI top10% vs Book</th>
                  <th className="py-1 pr-2">Evidenza ind.</th>
                  <th className="py-1 pr-2">ROI top10%</th>
                  <th className="py-1 pr-2">Stab. fold</th>
                  <th className="py-1">Decisione</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => {
                  const decision =
                    c.candidate_decision ||
                    decisionByConfig.get(
                      c.configuration.includes('ADVANTAGE')
                        ? 'probability_advantage'
                        : c.configuration.includes('EDGE')
                          ? 'edge'
                          : c.configuration.includes('SCORE')
                            ? 'score'
                            : c.configuration.includes('CONTEXT')
                              ? 'favourite_alignment'
                              : c.configuration.includes('RATING')
                                ? 'rating'
                                : c.configuration.includes('MODEL')
                                  ? 'model_probability'
                                  : '',
                    ) ||
                    'insufficient_evidence'
                  return (
                    <tr key={c.configuration} className="border-b border-slate-100">
                      <td className="py-1.5 pr-2 font-medium">{c.configuration}</td>
                      <td className="py-1.5 pr-2">{fmt(c.auc_mean)}</td>
                      <td className="py-1.5 pr-2">{c.contains_book_information ? 'sì' : 'no'}</td>
                      <td className="py-1.5 pr-2">
                        {fmt(c.independent_delta_auc_vs_book ?? c.delta_auc_vs_book_mean)}
                      </td>
                      <td className="py-1.5 pr-2">
                        {fmt(c.independent_delta_brier_vs_book ?? c.delta_brier_vs_book_mean)}
                      </td>
                      <td className="py-1.5 pr-2">{fmt(c.independent_roi_top_10_vs_book)}</td>
                      <td className="py-1.5 pr-2 text-xs">
                        {c.independent_evidence_status || '—'}
                      </td>
                      <td className="py-1.5 pr-2">{fmt(c.roi_top_10pct_mean)}</td>
                      <td className="py-1.5 pr-2">{c.temporal_stability || '—'}</td>
                      <td className="py-1.5 text-xs">{decision}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Confronti paired (Δ + CI)</h3>
            <table className="mt-3 w-full min-w-[1400px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Mercato</th>
                  <th className="py-1 pr-2">Spec</th>
                  <th className="py-1 pr-2">Baseline</th>
                  <th className="py-1 pr-2">Ruolo</th>
                  <th className="py-1 pr-2">ΔAUC</th>
                  <th className="py-1 pr-2">CI AUC</th>
                  <th className="py-1 pr-2">ΔBrier</th>
                  <th className="py-1 pr-2">ΔLL</th>
                  <th className="py-1 pr-2">ΔROI top10%</th>
                  <th className="py-1 pr-2">Fold +/-</th>
                  <th className="py-1 pr-2">Effect</th>
                  <th className="py-1 pr-2">Temporal</th>
                  <th className="py-1">Market</th>
                </tr>
              </thead>
              <tbody>
                {(data.marginal_contribution || []).slice(0, 80).map((m, i) => {
                  const ci = m.confidence_intervals?.delta_auc
                  return (
                    <tr key={`${m.market}-${m.spec}-${m.vs}-${i}`} className="border-b border-slate-100">
                      <td className="py-1.5 pr-2">{m.market}</td>
                      <td className="py-1.5 pr-2 text-xs">{m.spec}</td>
                      <td className="py-1.5 pr-2 text-xs">{m.vs}</td>
                      <td className="py-1.5 pr-2 text-xs">{m.comparison_role || '—'}</td>
                      <td className="py-1.5 pr-2">{fmt(m.delta_auc)}</td>
                      <td className="py-1.5 pr-2 text-xs">
                        [{fmt(ci?.ci_low)} , {fmt(ci?.ci_high)}]
                      </td>
                      <td className="py-1.5 pr-2">{fmt(m.delta_brier_improvement)}</td>
                      <td className="py-1.5 pr-2">{fmt(m.delta_log_loss_improvement)}</td>
                      <td className="py-1.5 pr-2">{fmt(m.delta_roi_top_10pct)}</td>
                      <td className="py-1.5 pr-2">
                        {m.positive_folds ?? 0}/{m.negative_folds ?? 0}
                      </td>
                      <td className="py-1.5 pr-2 text-xs">
                        {m.effect_classification || m.classification || '—'}
                      </td>
                      <td className="py-1.5 pr-2 text-xs">{m.temporal_classification || '—'}</td>
                      <td className="py-1.5 text-xs">
                        {m.market_classification || m.market_stability || '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Variabili</h3>
            <table className="mt-3 w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Feature</th>
                  <th className="py-1 pr-2">Decisione</th>
                  <th className="py-1 pr-2">vs Book</th>
                  <th className="py-1 pr-2">vs Model</th>
                  <th className="py-1 pr-2">Temp.</th>
                  <th className="py-1">Motivazione</th>
                </tr>
              </thead>
              <tbody>
                {(data.feature_decisions || []).map((f) => (
                  <tr key={f.feature_name} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2 font-medium">{f.feature_name}</td>
                    <td className="py-1.5 pr-2">{f.decision}</td>
                    <td className="py-1.5 pr-2 text-xs">
                      {f.evidence_axes?.incremental_vs_book ? 'sì' : 'no'}
                    </td>
                    <td className="py-1.5 pr-2 text-xs">
                      {f.evidence_axes?.incremental_vs_model ? 'sì' : 'no'}
                    </td>
                    <td className="py-1.5 pr-2">{f.temporal_stability || '—'}</td>
                    <td className="py-1.5 text-xs text-slate-600">{f.decision_reason || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-slate-900">
              Rating — benchmark specifico per mercato
            </h3>
            <p className="mt-2 text-sm text-slate-700">
              Conclusione benchmark:{' '}
              <span className="font-medium">{rating?.conclusion || '—'}</span>
            </p>
            <p className="mt-1 text-xs text-slate-500">{rating?.note}</p>
            <ul className="mt-3 space-y-2 text-sm">
              {(rating?.per_market || []).slice(0, 8).map((m) => (
                <li key={String(m.market)} className="border-b border-slate-100 pb-2">
                  <div className="font-medium">
                    {String(m.market)} — {String(m.decision || '')}
                  </div>
                  <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
                    {((m.prespecified_comparisons as Array<Record<string, unknown>>) || [])
                      .slice(0, 6)
                      .map((c, idx) => {
                        const ci = c.ci as { ci_low?: number; ci_high?: number } | undefined
                        return (
                          <li key={idx}>
                            {String(c.spec)} vs {String(c.vs)}: ΔAUC {fmt(c.delta_auc as number | null)}{' '}
                            CI [{fmt(ci?.ci_low)} , {fmt(ci?.ci_high)}] —{' '}
                            {String(c.temporal_classification || '')}
                          </li>
                        )
                      })}
                  </ul>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Mercati</h3>
            <table className="mt-3 w-full min-w-[1100px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Mercato</th>
                  <th className="py-1 pr-2">Rows</th>
                  <th className="py-1 pr-2">Fixture</th>
                  <th className="py-1 pr-2">WR</th>
                  <th className="py-1 pr-2">ROI coorte</th>
                  <th className="py-1 pr-2">Quota</th>
                  <th className="py-1 pr-2">AUC Book</th>
                  <th className="py-1 pr-2">Best AUC</th>
                  <th className="py-1 pr-2">Best spec</th>
                  <th className="py-1">Limitazioni</th>
                </tr>
              </thead>
              <tbody>
                {(data.market_results || []).map((m) => {
                  const specs = (m as { candidate_specifications?: Record<string, { classification?: { auc?: number } }> })
                    .candidate_specifications
                  const bookAuc = specs?.BOOK_BASELINE?.classification?.auc ?? null
                  return (
                    <tr key={m.market} className="border-b border-slate-100">
                      <td className="py-1.5 pr-2 font-medium">{m.market}</td>
                      <td className="py-1.5 pr-2">{m.settled_rows ?? 0}</td>
                      <td className="py-1.5 pr-2">{m.unique_fixtures ?? 0}</td>
                      <td className="py-1.5 pr-2">{fmt(m.win_rate)}</td>
                      <td
                        className="py-1.5 pr-2 text-slate-500"
                        title="ROI coorte — non discriminante"
                      >
                        {fmt(m.cohort_full_coverage_roi ?? m.roi)}
                      </td>
                      <td className="py-1.5 pr-2">{fmt(m.avg_odds, 2)}</td>
                      <td className="py-1.5 pr-2">{fmt(bookAuc)}</td>
                      <td className="py-1.5 pr-2">{fmt(m.best_spec_auc)}</td>
                      <td className="py-1.5 pr-2 text-xs">{m.best_spec_without_rating || '—'}</td>
                      <td className="py-1.5 text-xs text-slate-600">
                        {(m.limitations || []).join(', ') || '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Fold temporali</h3>
            <table className="mt-3 w-full min-w-[1200px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Fold</th>
                  <th className="py-1 pr-2">Train range</th>
                  <th className="py-1 pr-2">Test range</th>
                  <th className="py-1 pr-2">Train/Test fixture</th>
                  <th className="py-1 pr-2">Train/Test rows</th>
                  <th className="py-1 pr-2">Overlap</th>
                  <th className="py-1 pr-2">Train W/L/Void</th>
                  <th className="py-1 pr-2">Test W/L/Void</th>
                  <th className="py-1 pr-2">Train WR</th>
                  <th className="py-1">Test WR</th>
                </tr>
              </thead>
              <tbody>
                {(data.temporal_folds || []).map((f) => {
                  const cb = f.class_balance as
                    | {
                        train_won?: number
                        train_lost?: number
                        train_void?: number
                        test_won?: number
                        test_lost?: number
                        test_void?: number
                        train_win_rate?: number | null
                        test_win_rate?: number | null
                      }
                    | undefined
                  return (
                    <tr key={String(f.fold)} className="border-b border-slate-100">
                      <td className="py-1.5 pr-2">{String(f.fold)}</td>
                      <td className="py-1.5 pr-2">
                        {String(f.train_date_min || '—')} → {String(f.train_date_max || '—')}
                      </td>
                      <td className="py-1.5 pr-2">
                        {String(f.test_date_min || '—')} → {String(f.test_date_max || '—')}
                      </td>
                      <td className="py-1.5 pr-2">
                        {String(f.train_fixtures ?? (f.train_fixture_ids as unknown[] | undefined)?.length ?? '—')}{' '}
                        /{' '}
                        {String(f.test_fixtures ?? (f.test_fixture_ids as unknown[] | undefined)?.length ?? '—')}
                      </td>
                      <td className="py-1.5 pr-2">
                        {String(f.train_rows ?? '—')} / {String(f.test_rows ?? '—')}
                      </td>
                      <td className="py-1.5 pr-2">{String(f.fixture_overlap ?? 0)}</td>
                      <td className="py-1.5 pr-2">
                        {cb
                          ? `${cb.train_won ?? 0}/${cb.train_lost ?? 0}/${cb.train_void ?? 0}`
                          : '—'}
                      </td>
                      <td className="py-1.5 pr-2">
                        {cb
                          ? `${cb.test_won ?? 0}/${cb.test_lost ?? 0}/${cb.test_void ?? 0}`
                          : '—'}
                      </td>
                      <td className="py-1.5 pr-2">{fmt(cb?.train_win_rate)}</td>
                      <td className="py-1.5">{fmt(cb?.test_win_rate)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-900">Export Fase 2A.2</h3>
            <div className="flex flex-wrap gap-2">
              {EXPORTS.map(([kind, label]) => (
                <a
                  key={kind}
                  className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                  href={buildPurchasabilityStatExportUrl(kind, filters())}
                  target="_blank"
                  rel="noreferrer"
                >
                  {label}
                </a>
              ))}
            </div>
          </section>
        </>
      ) : (
        !loading && (
          <p className="text-sm text-slate-500">
            Imposta il range e avvia la ricerca statistica sulla coorte settled_core.
          </p>
        )
      )}
    </div>
  )
}
