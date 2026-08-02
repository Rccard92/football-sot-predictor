import type { HistoricalKpiSignalsFilters } from '../../../lib/cecchinoLabApi'
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

  return (
    <div
      className="sticky top-0 z-20 rounded-xl border p-3 backdrop-blur"
      style={{
        borderColor: 'var(--lab-border)',
        background: 'rgba(11,22,36,0.92)',
      }}
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
      </div>
    </div>
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
