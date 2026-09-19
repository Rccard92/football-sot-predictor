import { useId } from 'react'
import { todayCard, todayCardPadding } from '../cecchino/cecchinoTodayStyles'
import { V4_LEAGUES, v4Label } from './constants'

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

const inputCls =
  'min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 shadow-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-200'

export function V4Filters({ value, onChange }: Props) {
  const leagueId = useId()
  const set = (patch: Partial<V4FiltersValue>) => onChange({ ...value, ...patch })

  return (
    <section className={`${todayCard} ${todayCardPadding}`} aria-label="Filtri">
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex min-w-[220px] flex-col gap-1">
          <label htmlFor={leagueId} className={v4Label}>
            Campionato
          </label>
          <select
            id={leagueId}
            className={inputCls}
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
        </div>

        <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 text-base text-slate-800">
          <input
            type="checkbox"
            className="h-5 w-5 rounded border-slate-300 text-blue-600 focus:ring-blue-400"
            checked={value.onlyPlays}
            onChange={(e) => set({ onlyPlays: e.target.checked })}
          />
          Solo con giocata
        </label>

        <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 text-base text-slate-800">
          <input
            type="checkbox"
            className="h-5 w-5 rounded border-slate-300 text-blue-600 focus:ring-blue-400"
            checked={value.onlyLineups}
            onChange={(e) => set({ onlyLineups: e.target.checked })}
          />
          Solo formazioni note
        </label>

        <div className="flex flex-col gap-1">
          <span className={v4Label}>Ordina per</span>
          <div
            className="inline-flex overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm"
            role="group"
            aria-label="Ordinamento"
          >
            {(
              [
                ['kickoff', 'Orario'],
                ['profit', 'Profitto atteso'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-pressed={value.sort === key}
                onClick={() => set({ sort: key })}
                className={`min-h-11 px-4 text-base font-medium transition ${
                  value.sort === key ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
