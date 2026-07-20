import type { HomeWinsCompleteness } from '../../lib/cecchinoHomeWinsApi'

type Props = {
  dateFrom: string
  dateTo: string
  country: string
  league: string
  team: string
  completeness: HomeWinsCompleteness
  countries?: string[]
  leagues?: string[]
  onDateFrom: (v: string) => void
  onDateTo: (v: string) => void
  onCountry: (v: string) => void
  onLeague: (v: string) => void
  onTeam: (v: string) => void
  onCompleteness: (v: HomeWinsCompleteness) => void
  onApply: () => void
  onReset: () => void
  loading?: boolean
}

const inputCls =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-200'

export function HomeWinsFiltersBar({
  dateFrom,
  dateTo,
  country,
  league,
  team,
  completeness,
  countries = [],
  leagues = [],
  onDateFrom,
  onDateTo,
  onCountry,
  onLeague,
  onTeam,
  onCompleteness,
  onApply,
  onReset,
  loading,
}: Props) {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label className="block text-xs font-medium text-slate-600">
          Data da
          <input
            type="date"
            className={`mt-1 ${inputCls}`}
            value={dateFrom}
            onChange={(e) => onDateFrom(e.target.value)}
          />
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Data a
          <input
            type="date"
            className={`mt-1 ${inputCls}`}
            value={dateTo}
            onChange={(e) => onDateTo(e.target.value)}
          />
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Paese
          <input
            list="home-wins-countries"
            className={`mt-1 ${inputCls}`}
            value={country}
            onChange={(e) => onCountry(e.target.value)}
            placeholder="Es. Italy"
          />
          <datalist id="home-wins-countries">
            {countries.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Competizione
          <input
            list="home-wins-leagues"
            className={`mt-1 ${inputCls}`}
            value={league}
            onChange={(e) => onLeague(e.target.value)}
            placeholder="Es. Serie A"
          />
          <datalist id="home-wins-leagues">
            {leagues.map((l) => (
              <option key={l} value={l} />
            ))}
          </datalist>
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Squadra
          <input
            className={`mt-1 ${inputCls}`}
            value={team}
            onChange={(e) => onTeam(e.target.value)}
            placeholder="Casa o trasferta"
          />
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Completezza dati
          <select
            className={`mt-1 ${inputCls}`}
            value={completeness}
            onChange={(e) => onCompleteness(e.target.value as HomeWinsCompleteness)}
          >
            <option value="">Tutte</option>
            <option value="complete">Completi</option>
            <option value="partial">Parziali</option>
          </select>
        </label>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={loading}
          onClick={onApply}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
        >
          Applica filtri
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={onReset}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Reset filtri
        </button>
      </div>
    </div>
  )
}
