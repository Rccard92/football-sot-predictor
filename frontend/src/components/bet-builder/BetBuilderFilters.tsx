import { BET_BUILDER_MARKET_CHIPS } from '../../lib/cecchinoBetBuilderApi'
import {
  bbCard,
  bbCardPadding,
  bbChipActive,
  bbChipIdle,
  bbInput,
  bbSelect,
} from './betBuilderStyles'
import type {
  BetBuilderFilterState,
  BetBuilderMarketFilter,
  BetBuilderOriginFilter,
  BetBuilderSortKey,
} from './betBuilderUtils'

type Props = {
  filters: BetBuilderFilterState
  byMarket: Record<string, number>
  countries: string[]
  leagues: string[]
  secondaryOpen: boolean
  onToggleSecondary: () => void
  onChange: (patch: Partial<BetBuilderFilterState>) => void
}

const ORIGIN_OPTIONS: Array<{ key: BetBuilderOriginFilter; label: string }> = [
  { key: 'all', label: 'Tutte' },
  { key: 'price', label: 'Quota' },
  { key: 'signals', label: 'Segnali' },
  { key: 'price_and_signals', label: 'Quota + Segnali' },
]

const SORT_OPTIONS: Array<{ key: BetBuilderSortKey; label: string }> = [
  { key: 'purchasability_desc', label: 'Acquistabilità ↓' },
  { key: 'signals_desc', label: 'Segnali ↓' },
  { key: 'edge_desc', label: 'Edge ↓' },
  { key: 'kickoff_asc', label: 'Kickoff ↑' },
]

export function BetBuilderFilters({
  filters,
  byMarket,
  countries,
  leagues,
  secondaryOpen,
  onToggleSecondary,
  onChange,
}: Props) {
  return (
    <section className="space-y-4" aria-label="Filtri Bet Builder">
      <div className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-800">Mercati</h2>
        <div
          className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1"
          role="tablist"
          aria-label="Filtro mercato"
        >
          {BET_BUILDER_MARKET_CHIPS.map((chip) => {
            const active = filters.market === chip.key
            const count =
              chip.key === 'all'
                ? Object.values(byMarket).reduce((a, b) => a + (typeof b === 'number' ? b : 0), 0)
                : (byMarket[chip.key] ?? 0)
            return (
              <button
                key={chip.key}
                type="button"
                role="tab"
                aria-selected={active}
                aria-label={`${chip.label}, ${count}`}
                className={active ? bbChipActive : bbChipIdle}
                onClick={() => onChange({ market: chip.key as BetBuilderMarketFilter })}
              >
                <span>{chip.label}</span>
                <span className={active ? 'text-slate-300' : 'text-slate-400'} aria-hidden>
                  ·
                </span>
                <span className="tabular-nums" aria-hidden>
                  {count}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-800">Origine</h2>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filtro origine">
          {ORIGIN_OPTIONS.map((opt) => {
            const active = filters.origin === opt.key
            return (
              <button
                key={opt.key}
                type="button"
                aria-pressed={active}
                className={active ? bbChipActive : bbChipIdle}
                onClick={() => onChange({ origin: opt.key })}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className={`${bbCard} ${bbCardPadding} space-y-3`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-800">Altri filtri e ordinamento</h2>
          <button
            type="button"
            className="min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
            onClick={onToggleSecondary}
            aria-expanded={secondaryOpen}
          >
            {secondaryOpen ? 'Nascondi filtri' : 'Mostra filtri'}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block space-y-1">
            <span className="text-xs font-semibold text-slate-500">Ordinamento</span>
            <select
              className={bbSelect}
              value={filters.sort}
              onChange={(e) => onChange({ sort: e.target.value as BetBuilderSortKey })}
              aria-label="Ordinamento opportunity"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>

          {secondaryOpen ? (
            <>
              <label className="block space-y-1">
                <span className="text-xs font-semibold text-slate-500">Paese</span>
                <select
                  className={bbSelect}
                  value={filters.country}
                  onChange={(e) => onChange({ country: e.target.value, league: '' })}
                  aria-label="Filtro paese"
                >
                  <option value="">Tutti</option>
                  {countries.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block space-y-1">
                <span className="text-xs font-semibold text-slate-500">Campionato</span>
                <select
                  className={bbSelect}
                  value={filters.league}
                  onChange={(e) => onChange({ league: e.target.value })}
                  aria-label="Filtro campionato"
                >
                  <option value="">Tutti</option>
                  {leagues.map((l) => (
                    <option key={l} value={l}>
                      {l}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block space-y-1">
                <span className="text-xs font-semibold text-slate-500">Ricerca squadra</span>
                <input
                  className={bbInput}
                  type="search"
                  value={filters.search}
                  onChange={(e) => onChange({ search: e.target.value })}
                  placeholder="Nome squadra…"
                  aria-label="Ricerca squadra"
                />
              </label>

              <label className="block space-y-1 sm:col-span-2 lg:col-span-1">
                <span className="text-xs font-semibold text-slate-500">
                  Acquistabilità minima (opzionale)
                </span>
                <select
                  className={bbSelect}
                  value={filters.minPurchasability == null ? '' : String(filters.minPurchasability)}
                  onChange={(e) =>
                    onChange({
                      minPurchasability: e.target.value === '' ? null : Number(e.target.value),
                    })
                  }
                  aria-label="Acquistabilità minima"
                >
                  <option value="">Nessun filtro</option>
                  <option value="40">≥ 40</option>
                  <option value="55">≥ 55</option>
                  <option value="70">≥ 70</option>
                  <option value="85">≥ 85</option>
                </select>
              </label>
            </>
          ) : null}
        </div>
      </div>
    </section>
  )
}
