import type {
  PurchasabilityStatExportKind,
  PurchasabilityStatFilters,
  PurchasabilityStatisticalResearchResponse,
} from '../../lib/cecchinoPurchasabilityStatisticalApi'
import { buildPurchasabilityStatExportUrl } from '../../lib/cecchinoPurchasabilityStatisticalApi'

type Props = {
  data: PurchasabilityStatisticalResearchResponse | null
  loading: boolean
  error: string | null
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

  return (
    <div className="space-y-4">
      <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        {data?.research_banner ||
          'Fase di ricerca statistica. Nessun Indice di Acquistabilità produttivo. Nessuna influenza sui Segnali Cecchino.'}
      </p>

      {error ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>
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
                <dt className="text-slate-500">Stato</dt>
                <dd className="font-medium">{data.status}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Readiness 2B</dt>
                <dd className="font-medium">{readiness?.recommended_next_step || '—'}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Rating decision</dt>
                <dd className="font-medium">{readiness?.rating_decision || rating?.conclusion || '—'}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Elapsed total ms</dt>
                <dd className="font-medium">{fmt(data.elapsed_ms?.total, 1)}</dd>
              </div>
            </dl>
            {(data.limitations || []).length > 0 ? (
              <p className="mt-3 text-xs text-amber-800">
                Limitazioni: {(data.limitations || []).join(', ')}
              </p>
            ) : null}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Candidati</h3>
            <table className="mt-3 w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Config</th>
                  <th className="py-1 pr-2">AUC</th>
                  <th className="py-1 pr-2">ROI</th>
                  <th className="py-1 pr-2">Δ vs Book</th>
                  <th className="py-1 pr-2">Stabilità</th>
                  <th className="py-1">Stato</th>
                </tr>
              </thead>
              <tbody>
                {(data.candidate_specifications || []).map((c) => (
                  <tr key={c.configuration} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2 font-medium">{c.configuration}</td>
                    <td className="py-1.5 pr-2">{fmt(c.auc_mean)}</td>
                    <td className="py-1.5 pr-2">{fmt(c.roi_mean)}</td>
                    <td className="py-1.5 pr-2">{fmt(c.delta_vs_book_mean)}</td>
                    <td className="py-1.5 pr-2">{c.stability || '—'}</td>
                    <td className="py-1.5">{c.status || '—'}</td>
                  </tr>
                ))}
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
                  <th className="py-1 pr-2">Marginale</th>
                  <th className="py-1 pr-2">Temp.</th>
                  <th className="py-1 pr-2">Mercato</th>
                  <th className="py-1">Motivazione</th>
                </tr>
              </thead>
              <tbody>
                {(data.feature_decisions || []).map((f) => (
                  <tr key={f.feature_name} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2 font-medium">{f.feature_name}</td>
                    <td className="py-1.5 pr-2">{f.decision}</td>
                    <td className="py-1.5 pr-2 text-xs">
                      {(f.marginal_effect || []).slice(0, 2).join(', ') || '—'}
                    </td>
                    <td className="py-1.5 pr-2">{f.temporal_stability || '—'}</td>
                    <td className="py-1.5 pr-2">{f.market_stability || '—'}</td>
                    <td className="py-1.5 text-xs text-slate-600">{f.decision_reason || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-slate-900">Rating</h3>
            <p className="mt-2 text-sm text-slate-700">
              Conclusione: <span className="font-medium">{rating?.conclusion || '—'}</span>
            </p>
            <p className="mt-1 text-xs text-slate-500">{rating?.note}</p>
            <ul className="mt-3 space-y-1 text-sm">
              {(rating?.per_market || []).slice(0, 12).map((m) => (
                <li key={String(m.market)} className="flex flex-wrap gap-3 text-slate-700">
                  <span className="font-medium w-28">{String(m.market)}</span>
                  <span>alone {fmt(m.rating_alone_auc as number | null)}</span>
                  <span>best w/o {fmt(m.best_without_rating_auc as number | null)}</span>
                  <span>+rating {fmt(m.with_rating_auc as number | null)}</span>
                  <span>Δ {fmt(m.delta_auc_adding_rating as number | null)}</span>
                  <span>{String(m.decision || '')}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Mercati</h3>
            <table className="mt-3 w-full min-w-[800px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Mercato</th>
                  <th className="py-1 pr-2">Rows</th>
                  <th className="py-1 pr-2">Fixture</th>
                  <th className="py-1 pr-2">WR</th>
                  <th className="py-1 pr-2">ROI</th>
                  <th className="py-1 pr-2">Quota</th>
                  <th className="py-1 pr-2">Best spec</th>
                  <th className="py-1">AUC</th>
                </tr>
              </thead>
              <tbody>
                {(data.market_results || []).map((m) => (
                  <tr key={m.market} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2 font-medium">{m.market}</td>
                    <td className="py-1.5 pr-2">{m.settled_rows ?? 0}</td>
                    <td className="py-1.5 pr-2">{m.unique_fixtures ?? 0}</td>
                    <td className="py-1.5 pr-2">{fmt(m.win_rate)}</td>
                    <td className="py-1.5 pr-2">{fmt(m.roi)}</td>
                    <td className="py-1.5 pr-2">{fmt(m.avg_odds, 2)}</td>
                    <td className="py-1.5 pr-2">{m.best_spec_without_rating || '—'}</td>
                    <td className="py-1.5">{fmt(m.best_spec_auc)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
            <h3 className="text-sm font-semibold text-slate-900">Fold temporali</h3>
            <table className="mt-3 w-full min-w-[700px] text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Fold</th>
                  <th className="py-1 pr-2">Train range</th>
                  <th className="py-1 pr-2">Test range</th>
                  <th className="py-1 pr-2">Train/Test rows</th>
                  <th className="py-1">Overlap fixture</th>
                </tr>
              </thead>
              <tbody>
                {(data.temporal_folds || []).map((f) => (
                  <tr key={String(f.fold)} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2">{String(f.fold)}</td>
                    <td className="py-1.5 pr-2">
                      {String(f.train_date_min || '—')} → {String(f.train_date_max || '—')}
                    </td>
                    <td className="py-1.5 pr-2">
                      {String(f.test_date_min || '—')} → {String(f.test_date_max || '—')}
                    </td>
                    <td className="py-1.5 pr-2">
                      {String(f.train_rows ?? '—')} / {String(f.test_rows ?? '—')}
                    </td>
                    <td className="py-1.5">{String(f.fixture_overlap ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-900">Export Fase 2A</h3>
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
