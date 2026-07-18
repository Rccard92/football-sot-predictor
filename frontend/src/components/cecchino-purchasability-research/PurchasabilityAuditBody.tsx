import type {
  PurchasabilityAuditFilters,
  PurchasabilityAuditResponse,
  PurchasabilityDatasetResponse,
  PurchasabilityExportKind,
} from '../../lib/cecchinoPurchasabilityResearchApi'
import { buildPurchasabilityExportUrl } from '../../lib/cecchinoPurchasabilityResearchApi'

type Props = {
  audit: PurchasabilityAuditResponse | null
  dataset: PurchasabilityDatasetResponse | null
  loading: boolean
  error: string | null
  dateFrom: string
  dateTo: string
  marketFamily: string
  onDateFrom: (v: string) => void
  onDateTo: (v: string) => void
  onMarketFamily: (v: string) => void
  onRefresh: () => void
  onDatasetPage: (offset: number) => void
  filters: () => PurchasabilityAuditFilters
}

const EXPORTS: Array<[PurchasabilityExportKind, string]> = [
  ['audit_summary', 'Summary JSON'],
  ['variable_registry', 'Variabili CSV'],
  ['market_opposition_map', 'Opposizioni CSV'],
  ['market_coverage', 'Copertura CSV'],
  ['dataset', 'Dataset CSV'],
  ['exclusions', 'Esclusioni CSV'],
  ['rating_dependency_map', 'Rating map JSON'],
]

export function PurchasabilityAuditBody({
  audit,
  dataset,
  loading,
  error,
  dateFrom,
  dateTo,
  marketFamily,
  onDateFrom,
  onDateTo,
  onMarketFamily,
  onRefresh,
  onDatasetPage,
  filters,
}: Props) {
  const summary = audit?.summary
  const readiness = audit?.phase_2_readiness || {}
  const blocking = (readiness.blocking_issues as string[] | undefined) || []

  return (
    <div className="space-y-4">
      <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        Fase di audit research. Nessun Indice di Acquistabilità calcolato. Nessuna influenza sui
        Segnali Cecchino.
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
              Famiglia mercato
              <input
                className="ml-2 rounded border border-slate-300 px-2 py-1"
                placeholder="opzionale"
                value={marketFamily}
                onChange={(e) => onMarketFamily(e.target.value)}
              />
            </label>
          </div>
          <button
            type="button"
            disabled={loading}
            onClick={() => onRefresh()}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {loading ? 'Calcolo…' : 'Aggiorna Audit'}
          </button>
        </div>

        {summary ? (
          <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Versione audit" value={audit?.version ?? '—'} />
            <Stat label="Stato" value={audit?.status ?? '—'} />
            <Stat
              label="Intervallo"
              value={`${summary.date_min ?? '—'} → ${summary.date_max ?? '—'}`}
            />
            <Stat label="Osservate" value={String(summary.observed_rows)} />
            <Stat label="Core" value={String(summary.core_rows)} />
            <Stat label="Settled" value={String(summary.settled_core_rows)} />
            <Stat label="Mercati pronti" value={(summary.markets_ready || []).join(', ') || '—'} />
            <Stat label="Blocking" value={blocking.length ? blocking.join(', ') : 'nessuno'} />
            <Stat
              label="Readiness Fase 2"
              value={String(readiness.recommended_next_step ?? '—')}
            />
          </dl>
        ) : (
          <p className="mt-3 text-sm text-slate-500">Esegui «Aggiorna Audit» per caricare i dati.</p>
        )}

        <div className="mt-3 flex flex-wrap gap-1">
          {EXPORTS.map(([kind, label]) => (
            <a
              key={kind}
              href={buildPurchasabilityExportUrl(kind, filters())}
              target="_blank"
              rel="noreferrer"
              className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
            >
              {label}
            </a>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
        <h3 className="text-sm font-semibold text-slate-900">Variabili</h3>
        <table className="mt-2 w-full min-w-[800px] text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-2">Variabile</th>
              <th className="py-1 pr-2">Origine</th>
              <th className="py-1 pr-2">Persistenza</th>
              <th className="py-1 pr-2">Pre-match</th>
              <th className="py-1 pr-2">Indipendenza</th>
              <th className="py-1 pr-2">Leakage</th>
              <th className="py-1 pr-2">Stato</th>
              <th className="py-1">Motivazione</th>
            </tr>
          </thead>
          <tbody>
            {(audit?.variable_registry || []).map((v) => (
              <tr key={v.canonical_name} className="border-t border-slate-100 text-slate-800">
                <td className="py-1 pr-2 font-medium">{v.canonical_name}</td>
                <td className="py-1 pr-2">{v.source_field ?? '—'}</td>
                <td className="py-1 pr-2">{v.persistence}</td>
                <td className="py-1 pr-2">{v.pre_match_available ? 'sì' : 'no'}</td>
                <td className="py-1 pr-2">{v.independence_class}</td>
                <td className="py-1 pr-2">{v.leakage_risk}</td>
                <td className="py-1 pr-2">{v.audit_status}</td>
                <td className="py-1">{v.motivation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
        <h3 className="text-sm font-semibold text-slate-900">Mercati</h3>
        <table className="mt-2 w-full min-w-[700px] text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-2">Raw</th>
              <th className="py-1 pr-2">Famiglia</th>
              <th className="py-1 pr-2">Periodo</th>
              <th className="py-1 pr-2">Linea</th>
              <th className="py-1 pr-2">Comparatori</th>
              <th className="py-1 pr-2">Complemento</th>
              <th className="py-1 pr-2">Core</th>
              <th className="py-1">Stato</th>
            </tr>
          </thead>
          <tbody>
            {(audit?.market_coverage || []).map((m) => (
              <tr key={m.raw_market_code} className="border-t border-slate-100 text-slate-800">
                <td className="py-1 pr-2 font-medium">{m.raw_market_code}</td>
                <td className="py-1 pr-2">{m.canonical_market_family}</td>
                <td className="py-1 pr-2">{m.period}</td>
                <td className="py-1 pr-2">{m.line ?? '—'}</td>
                <td className="py-1 pr-2">{(m.comparator_selections || []).join(', ') || '—'}</td>
                <td className="py-1 pr-2">{m.complement_selection ?? '—'}</td>
                <td className="py-1 pr-2">{m.core_rows ?? 0}</td>
                <td className="py-1">{m.opposition_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 overflow-x-auto">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Dataset (campione core)</h3>
          <div className="flex gap-2 text-xs">
            <button
              type="button"
              className="rounded border border-slate-300 px-2 py-1 disabled:opacity-40"
              disabled={!dataset || dataset.offset <= 0 || loading}
              onClick={() => onDatasetPage(Math.max(0, (dataset?.offset ?? 0) - 50))}
            >
              Prec
            </button>
            <span className="text-slate-600">
              {dataset ? `${dataset.offset + 1}–${dataset.offset + dataset.items.length} / ${dataset.total}` : '—'}
            </span>
            <button
              type="button"
              className="rounded border border-slate-300 px-2 py-1 disabled:opacity-40"
              disabled={
                !dataset || dataset.offset + dataset.items.length >= dataset.total || loading
              }
              onClick={() => onDatasetPage((dataset?.offset ?? 0) + 50)}
            >
              Succ
            </button>
          </div>
        </div>
        <table className="mt-2 w-full min-w-[700px] text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-2">Partita</th>
              <th className="py-1 pr-2">Selezione</th>
              <th className="py-1 pr-2">Quota</th>
              <th className="py-1 pr-2">Rating</th>
              <th className="py-1 pr-2">Edge</th>
              <th className="py-1 pr-2">Settlement</th>
              <th className="py-1">Profit</th>
            </tr>
          </thead>
          <tbody>
            {(dataset?.items || []).map((r) => (
              <tr key={r.canonical_row_key || `${r.today_fixture_id}-${r.selection}`} className="border-t border-slate-100">
                <td className="py-1 pr-2">
                  {r.home_team}–{r.away_team}
                </td>
                <td className="py-1 pr-2">{r.selection}</td>
                <td className="py-1 pr-2">{r.odds ?? '—'}</td>
                <td className="py-1 pr-2">{r.rating ?? '—'}</td>
                <td className="py-1 pr-2">{r.edge ?? '—'}</td>
                <td className="py-1 pr-2">{r.settlement_status}</td>
                <td className="py-1">{r.unit_stake_profit ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-900 break-all">{value}</dd>
    </div>
  )
}
