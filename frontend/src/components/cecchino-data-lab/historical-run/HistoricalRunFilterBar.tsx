import type { HistoricalRunFilters } from '../../../lib/cecchinoLabApi'

type Props = {
  filters: HistoricalRunFilters
  competitions: string[]
  eligibleSample?: number
  isProvisional?: boolean
  onChange: (next: HistoricalRunFilters) => void
  onReset: () => void
}

const MARKETS = [
  'HOME',
  'DRAW',
  'AWAY',
  'OVER_1_5',
  'OVER_2_5',
  'UNDER_2_5',
  'UNDER_3_5',
]

const RATING_BANDS = ['lt_50', '50-59', '60-69', '70-79', '80-89', '90-99', '100', 'unavailable']

export function HistoricalRunFilterBar({
  filters,
  competitions,
  eligibleSample,
  isProvisional,
  onChange,
  onReset,
}: Props) {
  function set<K extends keyof HistoricalRunFilters>(key: K, value: string) {
    onChange({ ...filters, [key]: value || undefined })
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
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-medium text-[var(--lab-cyan)]">Filtri globali</span>
          {eligibleSample != null ? (
            <span className="text-[var(--lab-muted)]">
              Campione attivo: {eligibleSample} eleggibili
            </span>
          ) : null}
          {isProvisional ? (
            <span className="rounded px-2 py-0.5" style={{ background: 'rgba(46,230,255,0.15)' }}>
              Dati provvisori
            </span>
          ) : (
            <span className="rounded px-2 py-0.5" style={{ background: 'rgba(61,214,140,0.15)' }}>
              Risultati congelati
            </span>
          )}
        </div>
        <button type="button" className="text-xs underline" onClick={onReset}>
          Reset filtri
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-6">
        <Select
          label="Campionato"
          value={filters.competition ?? ''}
          onChange={(v) => set('competition', v)}
          options={competitions.map((c) => ({ value: c, label: c }))}
        />
        <Field
          label="Da"
          type="date"
          value={filters.date_from ?? ''}
          onChange={(v) => set('date_from', v)}
        />
        <Field
          label="A"
          type="date"
          value={filters.date_to ?? ''}
          onChange={(v) => set('date_to', v)}
        />
        <Select
          label="Mercato"
          value={filters.market_key ?? ''}
          onChange={(v) => set('market_key', v)}
          options={MARKETS.map((m) => ({ value: m, label: m }))}
        />
        <Select
          label="Rating"
          value={filters.rating_band ?? ''}
          onChange={(v) => set('rating_band', v)}
          options={RATING_BANDS.map((b) => ({ value: b, label: b }))}
        />
        <Select
          label="Acquistabilità"
          value={filters.purchasability_band ?? ''}
          onChange={(v) => set('purchasability_band', v)}
          options={[
            '0-9',
            '10-19',
            '20-29',
            '30-39',
            '40-49',
            '50-59',
            '60-69',
            '70-79',
            '80-89',
            '90-99',
            '100',
            'unavailable',
          ].map((b) => ({ value: b, label: b }))}
        />
        <Select
          label="Modello"
          value={filters.signal_model ?? ''}
          onChange={(v) => set('signal_model', v)}
          options={['A', 'B', 'C', 'D', 'E', 'F'].map((m) => ({ value: m, label: m }))}
        />
        <Select
          label="Segnale attivo"
          value={filters.signal_active ?? ''}
          onChange={(v) => set('signal_active', v)}
          options={[
            { value: 'true', label: 'Sì' },
            { value: 'false', label: 'No' },
          ]}
        />
        <Select
          label="Quota"
          value={filters.quote_quality ?? ''}
          onChange={(v) => set('quote_quality', v)}
          options={[
            { value: 'real', label: 'Reale Bet365' },
            { value: 'derived', label: 'Derivata' },
            { value: 'unavailable', label: 'Non disponibile' },
          ]}
        />
        <Select
          label="Balance"
          value={filters.balance_class ?? ''}
          onChange={(v) => set('balance_class', v)}
          options={[
            { value: 'equilibrio', label: 'equilibrio' },
            { value: 'squilibrio', label: 'squilibrio' },
            { value: 'unknown', label: 'unknown' },
          ]}
        />
        <Select
          label="Intensità Goal"
          value={filters.goal_intensity_status ?? ''}
          onChange={(v) => set('goal_intensity_status', v)}
          options={[
            { value: 'computed', label: 'computed' },
            { value: 'insufficient_sample', label: 'insufficient_sample' },
            { value: 'unavailable', label: 'unavailable' },
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
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
}) {
  return (
    <label className="text-[11px] text-[var(--lab-muted)]">
      {label}
      <input
        className="lab-input mt-0.5 w-full text-sm"
        type={type}
        value={value}
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
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: Array<{ value: string; label: string }>
}) {
  return (
    <label className="text-[11px] text-[var(--lab-muted)]">
      {label}
      <select
        className="lab-input mt-0.5 w-full text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Tutti</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}
