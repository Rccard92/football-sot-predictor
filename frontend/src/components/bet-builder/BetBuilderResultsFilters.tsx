import { useId } from 'react'
import { BET_BUILDER_MARKET_CHIPS, BET_BUILDER_RESULTS_START_DATE } from '../../lib/cecchinoBetBuilderApi'
import { bbCard, bbCardPadding, bbChipActive, bbChipIdle, bbInput, bbSelect } from './betBuilderStyles'
import type { BetBuilderResultsFilterState, BetBuilderResultsOutcomeFilter } from './betBuilderResultsUtils'

type Props = {
  filters: BetBuilderResultsFilterState
  onChange: (patch: Partial<BetBuilderResultsFilterState>) => void
  /** Controlled so accordion survives Results reload on filter change. */
  filtersOpen: boolean
  onFiltersOpenChange: (open: boolean) => void
}

const OUTCOME_CHIPS: Array<{ key: BetBuilderResultsOutcomeFilter; label: string }> = [
  { key: 'all', label: 'Tutte' },
  { key: 'lost', label: 'Perse' },
  { key: 'won', label: 'Vinte' },
  { key: 'pending', label: 'In attesa' },
  { key: 'live', label: 'Live' },
]

export function BetBuilderResultsFilters({
  filters,
  onChange,
  filtersOpen,
  onFiltersOpenChange,
}: Props) {
  const panelId = useId()

  return (
    <section className={`${bbCard} ${bbCardPadding} space-y-3`} data-testid="bet-builder-results-filters">
      <button
        type="button"
        className="flex min-h-11 w-full items-center justify-between gap-2 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 lg:hidden"
        aria-expanded={filtersOpen}
        aria-controls={panelId}
        data-testid="results-filters-accordion"
        onClick={() => onFiltersOpenChange(!filtersOpen)}
      >
        <span className="text-sm font-semibold text-slate-800">Filtri risultati</span>
        <svg
          aria-hidden="true"
          className={`h-5 w-5 shrink-0 text-slate-500 motion-safe:transition-transform motion-reduce:transition-none ${
            filtersOpen ? 'rotate-180' : ''
          }`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      <div
        id={panelId}
        data-testid="results-filters-panel"
        className={`space-y-3 ${filtersOpen ? 'block' : 'hidden'} lg:block`}
      >
        <div className="flex flex-wrap items-end gap-2">
          <label className="block min-w-[9rem]">
            <span className="mb-1 block text-xs font-medium text-slate-500">Da</span>
            <input
              type="date"
              className={bbInput}
              min={BET_BUILDER_RESULTS_START_DATE}
              value={filters.dateFrom}
              data-testid="results-date-from"
              onChange={(e) => {
                if (e.target.value) onChange({ dateFrom: e.target.value })
              }}
            />
          </label>
          <label className="block min-w-[9rem]">
            <span className="mb-1 block text-xs font-medium text-slate-500">A</span>
            <input
              type="date"
              className={bbInput}
              min={BET_BUILDER_RESULTS_START_DATE}
              value={filters.dateTo}
              data-testid="results-date-to"
              onChange={(e) => {
                if (e.target.value) onChange({ dateTo: e.target.value })
              }}
            />
          </label>
          <label className="block min-w-[10rem]">
            <span className="mb-1 block text-xs font-medium text-slate-500">Ordina</span>
            <select
              className={bbSelect}
              value={filters.sort}
              data-testid="results-sort"
              onChange={(e) =>
                onChange({ sort: e.target.value as BetBuilderResultsFilterState['sort'] })
              }
            >
              <option value="recent">Più recenti</option>
              <option value="kickoff_asc">Inizio più vicino</option>
              <option value="lost_first">Perse prima</option>
              <option value="purchasability_desc">Acquistabilità DESC</option>
            </select>
          </label>
        </div>

        <div className="flex flex-wrap gap-2" role="group" aria-label="Filtro esito">
          {OUTCOME_CHIPS.map((chip) => (
            <button
              key={chip.key}
              type="button"
              data-testid={`results-outcome-${chip.key}`}
              className={filters.outcome === chip.key ? bbChipActive : bbChipIdle}
              onClick={() => onChange({ outcome: chip.key })}
            >
              {chip.label}
            </button>
          ))}
        </div>

        <div className="grid gap-2 sm:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">Mercato</span>
            <select
              className={bbSelect}
              value={filters.market}
              data-testid="results-market"
              onChange={(e) => onChange({ market: e.target.value })}
            >
              {BET_BUILDER_MARKET_CHIPS.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">Origin</span>
            <select
              className={bbSelect}
              value={filters.origin}
              data-testid="results-origin"
              onChange={(e) =>
                onChange({ origin: e.target.value as BetBuilderResultsFilterState['origin'] })
              }
            >
              <option value="all">Tutte</option>
              <option value="price_and_signals">Quota + Segnali</option>
              <option value="signals">Segnali</option>
              <option value="price">Quota</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">Acquistabilità min.</span>
            <input
              type="number"
              min={0}
              max={100}
              className={bbInput}
              placeholder="Es. 50"
              value={filters.minPurchasability ?? ''}
              data-testid="results-min-purch"
              onChange={(e) => {
                const v = e.target.value
                onChange({ minPurchasability: v === '' ? null : Number(v) })
              }}
            />
          </label>
        </div>
      </div>
    </section>
  )
}
