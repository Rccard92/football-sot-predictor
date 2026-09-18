import {
  bbCard,
  bbCardPadding,
  bbChipActive,
  bbChipIdle,
  bbInput,
  bbMarketChipScroll,
  bbSelect,
} from '../bet-builder/betBuilderStyles'
import {
  FAMILY_CHIPS,
  type BbV3FamilyFilter,
  type BbV3Filters,
  type BbV3OutcomeFilter,
  type BbV3SortKey,
  type BbV3Tab,
} from './bbV3Utils'

type Props = {
  filters: BbV3Filters
  counts: Record<BbV3FamilyFilter, number>
  countries: string[]
  leagues: string[]
  tab: BbV3Tab
  showOutcome: boolean
  secondaryOpen: boolean
  onToggleSecondary: () => void
  onChange: (patch: Partial<BbV3Filters>) => void
}

const SORT_OPTIONS: { key: BbV3SortKey; label: string }[] = [
  { key: 'score_desc', label: 'Punteggio ↓' },
  { key: 'kickoff_asc', label: 'Kickoff ↑' },
  { key: 'quota_desc', label: 'Quota ↓' },
]

const OUTCOME_OPTIONS: { key: BbV3OutcomeFilter; label: string }[] = [
  { key: 'all', label: 'Tutte' },
  { key: 'won', label: 'Vinte' },
  { key: 'lost', label: 'Perse' },
  { key: 'pending', label: 'In attesa' },
]

function countSecondary(f: BbV3Filters): number {
  return [f.country, f.league, f.minScore != null ? 'x' : ''].filter(Boolean).length
}

export function BetBuilderV3Filters({
  filters,
  counts,
  countries,
  leagues,
  tab,
  showOutcome,
  secondaryOpen,
  onToggleSecondary,
  onChange,
}: Props) {
  const activeSecondary = countSecondary(filters)
  const agreeLabel = tab === 'combo' ? 'Confermate da un pattern' : 'Indice + pattern d’accordo'

  return (
    <section className="space-y-2" aria-label="Filtri Bet Builder V3">
      <div className="space-y-1.5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Mercati</h2>
        <div className={bbMarketChipScroll} role="tablist" aria-label="Filtro mercato">
          {FAMILY_CHIPS.map((chip) => {
            const active = filters.family === chip.key
            return (
              <button
                key={chip.key}
                type="button"
                role="tab"
                aria-selected={active}
                className={`${active ? bbChipActive : bbChipIdle} snap-start min-h-9 py-1.5`}
                onClick={() => onChange({ family: chip.key })}
              >
                <span>{chip.label}</span>
                <span className={active ? 'text-slate-300' : 'text-slate-400'} aria-hidden>
                  ·
                </span>
                <span className="tabular-nums">{counts[chip.key]}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <label className="block min-w-0 flex-1 sm:max-w-xs">
          <span className="sr-only">Cerca squadra</span>
          <input
            className={bbInput}
            type="search"
            value={filters.search}
            onChange={(e) => onChange({ search: e.target.value })}
            placeholder="Cerca squadra…"
            aria-label="Ricerca squadra"
          />
        </label>

        <button
          type="button"
          aria-pressed={filters.patternAgree}
          className={filters.patternAgree ? bbChipActive : bbChipIdle}
          data-testid="bb-v3-filter-pattern-agree"
          onClick={() => onChange({ patternAgree: !filters.patternAgree })}
        >
          {agreeLabel}
        </button>

        <button
          type="button"
          aria-pressed={filters.playableOnly}
          className={filters.playableOnly ? bbChipActive : bbChipIdle}
          data-testid="bb-v3-filter-playable"
          onClick={() => onChange({ playableOnly: !filters.playableOnly })}
        >
          Solo giocabili (quota ≥ 1,50)
        </button>

        <button
          type="button"
          className={activeSecondary > 0 ? bbChipActive : bbChipIdle}
          onClick={onToggleSecondary}
          aria-expanded={secondaryOpen}
        >
          {activeSecondary > 0 ? `Filtri · ${activeSecondary}` : 'Filtri'}
        </button>

        <label className="flex items-center gap-2">
          <span className="sr-only">Ordina</span>
          <select
            className={`${bbSelect} w-auto min-w-[10rem]`}
            value={filters.sort}
            onChange={(e) => onChange({ sort: e.target.value as BbV3SortKey })}
            aria-label="Ordinamento"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {showOutcome ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filtro esito">
          {OUTCOME_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              aria-pressed={filters.outcome === opt.key}
              className={filters.outcome === opt.key ? bbChipActive : bbChipIdle}
              onClick={() => onChange({ outcome: opt.key })}
            >
              {opt.label}
            </button>
          ))}
        </div>
      ) : null}

      {secondaryOpen ? (
        <div className={`${bbCard} ${bbCardPadding} grid grid-cols-1 gap-3 sm:grid-cols-3`}>
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
            <span className="text-xs font-semibold text-slate-500">Punteggio minimo</span>
            <select
              className={bbSelect}
              value={filters.minScore == null ? '' : String(filters.minScore)}
              onChange={(e) => onChange({ minScore: e.target.value === '' ? null : Number(e.target.value) })}
              aria-label="Punteggio minimo"
            >
              <option value="">Da 70 (tutte le predizioni)</option>
              <option value="80">≥ 80</option>
              <option value="90">≥ 90</option>
            </select>
          </label>
        </div>
      ) : null}
    </section>
  )
}
