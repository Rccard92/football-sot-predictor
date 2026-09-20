import { useId } from 'react'
import { todayCard, todayCardPadding } from '../cecchino/cecchinoTodayStyles'
import { V4_LEAGUES, v4FilterChip, v4FilterChipOff, v4FilterChipOn } from './constants'

export type V4SortKey = 'kickoff' | 'profit'

export type V4FiltersValue = {
  league: string
  onlyPlays: boolean
  onlyLineups: boolean
  sort: V4SortKey
}

type Props = {
  value: V4FiltersValue
  onChange: (next: V4FiltersValue) => void
}

const SORT_OPTIONS: Array<{ value: V4SortKey; label: string }> = [
  { value: 'kickoff', label: 'Per orario' },
  { value: 'profit', label: 'Per profitto atteso' },
]

/** Filtri compatti come in CecchinoTodayFilters: chip, una tendina, due spunte. */
export function V4Filters({ value, onChange }: Props) {
  const leagueId = useId()
  const set = (patch: Partial<V4FiltersValue>) => onChange({ ...value, ...patch })

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-3`} aria-label="Filtri">
      <p className="text-sm font-medium text-slate-800">Filtri</p>
      <div className="flex flex-wrap items-center gap-2">
        {SORT_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            aria-pressed={value.sort === opt.value}
            onClick={() => set({ sort: opt.value })}
            className={`${v4FilterChip} ${value.sort === opt.value ? v4FilterChipOn : v4FilterChipOff}`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <select
          id={leagueId}
          aria-label="Campionato"
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-900"
          value={value.league}
          onChange={(e) => set({ league: e.target.value })}
        >
          <option value="">Tutti i campionati</option>
          {V4_LEAGUES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.competition} · {l.country}
            </option>
          ))}
        </select>

        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-400"
            checked={value.onlyPlays}
            onChange={(e) => set({ onlyPlays: e.target.checked })}
          />
          Solo con giocata
        </label>

        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-400"
            checked={value.onlyLineups}
            onChange={(e) => set({ onlyLineups: e.target.checked })}
          />
          Solo formazioni note
        </label>
      </div>
    </section>
  )
}
