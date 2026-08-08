import { BET_BUILDER_MARKET_CHIPS, BET_BUILDER_RESULTS_START_DATE } from '../../lib/cecchinoBetBuilderApi'
import { bbCard, bbCardPadding, bbChipActive, bbChipIdle, bbInput, bbPrimaryBtn, bbSelect } from './betBuilderStyles'
import type { BetBuilderResultsFilterState, BetBuilderResultsOutcomeFilter } from './betBuilderResultsUtils'

type Props = {
  filters: BetBuilderResultsFilterState
  onChange: (patch: Partial<BetBuilderResultsFilterState>) => void
  onAnalyzeLost: () => void
}

const OUTCOME_CHIPS: Array<{ key: BetBuilderResultsOutcomeFilter; label: string }> = [
  { key: 'all', label: 'Tutte' },
  { key: 'lost', label: 'Perse' },
  { key: 'won', label: 'Vinte' },
  { key: 'pending', label: 'In attesa' },
  { key: 'live', label: 'Live' },
]

export function BetBuilderResultsFilters({ filters, onChange, onAnalyzeLost }: Props) {
  return (
    <section className={`${bbCard} ${bbCardPadding} space-y-3`} data-testid="bet-builder-results-filters">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
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
        <button
          type="button"
          className={bbPrimaryBtn}
          data-testid="results-analyze-lost"
          onClick={onAnalyzeLost}
        >
          Analizza perse
        </button>
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
    </section>
  )
}
