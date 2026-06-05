import type { MatchDisplayStatus } from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding } from './cecchinoTodayStyles'

export type StatusFilter = 'all' | MatchDisplayStatus

type Props = {
  statusFilter: StatusFilter
  onStatusFilterChange: (v: StatusFilter) => void
  countryFilter: string
  onCountryFilterChange: (v: string) => void
  leagueFilter: string
  onLeagueFilterChange: (v: string) => void
  searchQuery: string
  onSearchQueryChange: (v: string) => void
  countries: string[]
  leagues: string[]
}

const STATUS_OPTIONS: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'Tutte' },
  { value: 'upcoming', label: 'Da giocare' },
  { value: 'live', label: 'Live' },
  { value: 'finished', label: 'Concluse' },
]

export function CecchinoTodayFilters({
  statusFilter,
  onStatusFilterChange,
  countryFilter,
  onCountryFilterChange,
  leagueFilter,
  onLeagueFilterChange,
  searchQuery,
  onSearchQueryChange,
  countries,
  leagues,
}: Props) {
  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-3`}>
      <p className="text-sm font-medium text-slate-800">Filtri</p>
      <div className="flex flex-wrap gap-2">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onStatusFilterChange(opt.value)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              statusFilter === opt.value
                ? 'bg-blue-600 text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        <select
          value={countryFilter}
          onChange={(e) => {
            onCountryFilterChange(e.target.value)
            onLeagueFilterChange('')
          }}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">Tutte le nazioni</option>
          {countries.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          value={leagueFilter}
          onChange={(e) => onLeagueFilterChange(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          disabled={!countryFilter && leagues.length === 0}
        >
          <option value="">Tutti i campionati</option>
          {leagues.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <input
          type="search"
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          placeholder="Cerca squadra, campionato…"
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
      </div>
    </section>
  )
}
