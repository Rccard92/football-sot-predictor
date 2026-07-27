import type { CecchinoLabAnalyticsOverview } from '../../../lib/cecchinoLabApi'

type Filters = {
  season_label: string
  country: string
  competition: string
}

type Props = {
  available: CecchinoLabAnalyticsOverview['available_filters'] | undefined
  filters: Filters
  sample: CecchinoLabAnalyticsOverview['sample'] | undefined
  onChange: (next: Filters) => void
  onReset: () => void
}

export function OverviewFilters({ available, filters, sample, onChange, onReset }: Props) {
  const competitions = (available?.competitions || []).filter(
    (c) => !filters.country || c.country === filters.country,
  )

  return (
    <div
      className="sticky top-0 z-30 -mx-4 mb-4 space-y-3 border-b px-4 py-3 backdrop-blur-md sm:-mx-6 sm:px-6"
      style={{
        background: 'linear-gradient(180deg, rgba(11,22,36,0.96) 0%, rgba(11,22,36,0.88) 100%)',
        borderColor: 'var(--lab-border)',
      }}
    >
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
          Stagione
          <select
            className="lab-input min-w-[140px]"
            value={filters.season_label}
            onChange={(e) => onChange({ ...filters, season_label: e.target.value })}
          >
            <option value="">Tutte le stagioni</option>
            {(available?.seasons || []).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
          Paese
          <select
            className="lab-input min-w-[140px]"
            value={filters.country}
            onChange={(e) =>
              onChange({
                ...filters,
                country: e.target.value,
                competition: '',
              })
            }
          >
            <option value="">Tutti i paesi</option>
            {(available?.countries || []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
          Campionato
          <select
            className="lab-input min-w-[180px]"
            value={filters.competition}
            onChange={(e) => onChange({ ...filters, competition: e.target.value })}
          >
            <option value="">Tutti i campionati</option>
            {competitions.map((c) => (
              <option key={`${c.country}-${c.name}`} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="lab-btn-ghost" onClick={onReset}>
          Reset filtri
        </button>
      </div>
      {sample ? (
        <div className="text-sm tabular-nums" style={{ color: 'var(--lab-cyan)' }}>
          {sample.matches_total.toLocaleString('it-IT')} partite · {sample.competitions_count}{' '}
          campionati · {sample.seasons_count} stagioni
        </div>
      ) : null}
    </div>
  )
}
