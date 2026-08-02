import type {
  HistoricalKpiSignalsFilters,
  PurchasabilityFilterImpact,
} from '../../../lib/cecchinoLabApi'
import { marketLabel, RATING_BUCKETS } from './historicalKpiUtils'

type AvailableFilters = {
  competitions: string[]
  selection_keys: string[]
  date_min: string | null
  date_max: string | null
}

type Props = {
  filters: HistoricalKpiSignalsFilters
  availableFilters: AvailableFilters
  onChange: (next: HistoricalKpiSignalsFilters) => void
  onRefresh: () => void
  onReset: () => void
}

const EVALUATION_STATUSES = [
  { value: 'won', label: 'Vinto' },
  { value: 'lost', label: 'Perso' },
  { value: 'settled', label: 'Regolato' },
  { value: 'pending', label: 'In attesa' },
  { value: 'void', label: 'Void' },
]

const PURCH_QUICK = [20, 40, 60, 70, 75, 80, 90]

export function HistoricalKpiSignalsFilters({
  filters,
  availableFilters,
  onChange,
  onRefresh,
  onReset,
}: Props) {
  function set<K extends keyof HistoricalKpiSignalsFilters>(key: K, value: string) {
    onChange({ ...filters, [key]: value || undefined })
  }

  function setQuoteType(value: string) {
    const qt =
      value === 'derived' || value === 'all'
        ? value
        : ('real' as HistoricalKpiSignalsFilters['quote_type'])
    onChange({ ...filters, quote_type: qt })
  }

  function setPurchMin(raw: string) {
    if (!raw.trim()) {
      onChange({ ...filters, purchasability_min_score: undefined })
      return
    }
    const n = Number(raw)
    if (!Number.isFinite(n)) return
    const clamped = Math.max(0, Math.min(100, Math.round(n)))
    onChange({ ...filters, purchasability_min_score: clamped })
  }

  const purchValue =
    filters.purchasability_min_score != null ? String(filters.purchasability_min_score) : ''

  return (
    <div
      className="sticky top-0 z-20 rounded-xl border p-3 backdrop-blur"
      style={{
        borderColor: 'var(--lab-border)',
        background: 'rgba(11,22,36,0.92)',
      }}
      data-testid="historical-kpi-filters"
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium text-[var(--lab-cyan)]">Filtri analisi KPI</span>
        <div className="flex gap-2">
          <button type="button" className="lab-btn text-xs" onClick={onRefresh}>
            Aggiorna
          </button>
          <button type="button" className="lab-btn-ghost text-xs" onClick={onReset}>
            Reset filtri
          </button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-8">
        <Field
          label="Da"
          type="date"
          value={filters.date_from ?? ''}
          min={availableFilters.date_min ?? undefined}
          max={availableFilters.date_max ?? undefined}
          onChange={(v) => set('date_from', v)}
        />
        <Field
          label="A"
          type="date"
          value={filters.date_to ?? ''}
          min={availableFilters.date_min ?? undefined}
          max={availableFilters.date_max ?? undefined}
          onChange={(v) => set('date_to', v)}
        />
        <Select
          label="Fascia rating"
          value={filters.rating_bucket ?? ''}
          onChange={(v) => set('rating_bucket', v)}
          options={RATING_BUCKETS.map((b) => ({ value: b, label: b }))}
        />
        <Select
          label="Mercato"
          value={filters.selection_key ?? ''}
          onChange={(v) => set('selection_key', v)}
          options={availableFilters.selection_keys.map((k) => ({
            value: k,
            label: marketLabel(k),
          }))}
        />
        <Select
          label="Valutazione"
          value={filters.evaluation_status ?? ''}
          onChange={(v) => set('evaluation_status', v)}
          options={EVALUATION_STATUSES}
        />
        <Select
          label="Campionato"
          value={filters.competition ?? ''}
          onChange={(v) => set('competition', v)}
          options={availableFilters.competitions.map((c) => ({ value: c, label: c }))}
        />
        <Select
          label="Tipo quota"
          value={filters.quote_type ?? 'real'}
          onChange={setQuoteType}
          includeAll={false}
          options={[
            { value: 'real', label: 'Quote reali' },
            { value: 'derived', label: 'Quote derivate' },
            { value: 'all', label: 'Tutte' },
          ]}
        />
        <label className="text-[11px] text-[var(--lab-muted)]">
          Acquistabilità V3 minima
          <input
            className="lab-input mt-0.5 w-full text-sm"
            type="number"
            min={0}
            max={100}
            placeholder="Nessun filtro"
            value={purchValue}
            data-testid="purchasability-min-score-input"
            onChange={(e) => setPurchMin(e.target.value)}
          />
        </label>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-[var(--lab-muted)]">Soglie rapide:</span>
        {PURCH_QUICK.map((n) => (
          <button
            key={n}
            type="button"
            className="lab-btn-ghost px-2 py-0.5 text-xs"
            data-testid={`purchasability-quick-${n}`}
            onClick={() => onChange({ ...filters, purchasability_min_score: n })}
          >
            {n}
          </button>
        ))}
        {filters.purchasability_min_score != null ? (
          <button
            type="button"
            className="lab-btn text-xs"
            data-testid="purchasability-remove-filter"
            onClick={() => onChange({ ...filters, purchasability_min_score: undefined })}
          >
            Rimuovi filtro Acquistabilità
          </button>
        ) : null}
      </div>
    </div>
  )
}

type ImpactProps = {
  impact: PurchasabilityFilterImpact
  unsupportedReason?: string | null
  message?: string | null
}

export function HistoricalKpiPurchasabilityImpactCard({
  impact,
  unsupportedReason,
  message,
}: ImpactProps) {
  if (!impact.enabled) return null
  const min = impact.min_score ?? 0
  return (
    <section
      className="lab-card rounded-xl p-4"
      data-testid="purchasability-impact-card"
    >
      <h3 className="text-base font-semibold">Impatto Acquistabilità V3</h3>
      <p className="mt-1 text-xs text-[var(--lab-muted)]">
        Il filtro V3 si applica solo ai mercati supportati dalla formula.
      </p>
      {unsupportedReason === 'purchasability_v3_market_not_supported' || message ? (
        <p className="mt-2 text-sm text-[var(--lab-warn)]" data-testid="purchasability-unsupported-warning">
          {message ||
            'Il mercato selezionato non è supportato dalla formula Acquistabilità V3.'}
        </p>
      ) : null}
      <div className="mt-3 space-y-1 text-sm">
        <p>
          {impact.base_signals_before_filter} segnali prima del filtro
          <span className="text-[var(--lab-muted)]"> → </span>
          {impact.v3_supported_and_joined} supportati dalla V3
          <span className="text-[var(--lab-muted)]"> → </span>
          {impact.v3_scored} con score disponibile
          <span className="text-[var(--lab-muted)]"> → </span>
          {impact.matched_threshold} con Acquistabilità ≥{min}
        </p>
        <p className="text-xs text-[var(--lab-muted)]">
          Percentuale rimasta: {impact.coverage_pct}% · esclusi gate:{' '}
          {impact.excluded_gate_failed} · non supportati:{' '}
          {impact.excluded_unsupported_market}
          {impact.official_replay_id != null
            ? ` · Replay ID ${impact.official_replay_id}`
            : ''}
          {impact.formula_version ? ` · ${impact.formula_version}` : ''}
        </p>
      </div>
    </section>
  )
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
  min,
  max,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
  min?: string
  max?: string
}) {
  return (
    <label className="text-[11px] text-[var(--lab-muted)]">
      {label}
      <input
        className="lab-input mt-0.5 w-full text-sm"
        type={type}
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}

function Select({
  label,
  value,
  onChange,
  options,
  includeAll = true,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: Array<{ value: string; label: string }>
  includeAll?: boolean
}) {
  return (
    <label className="text-[11px] text-[var(--lab-muted)]">
      {label}
      <select
        className="lab-input mt-0.5 w-full text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {includeAll ? <option value="">Tutti</option> : null}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}
