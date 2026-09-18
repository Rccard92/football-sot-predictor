import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BetBuilderV3FixtureCard } from '../components/bet-builder-v3/BetBuilderV3FixtureCard'
import { BetBuilderV3Filters } from '../components/bet-builder-v3/BetBuilderV3Filters'
import {
  BetBuilderV3PrematchSummary,
  BetBuilderV3ResultsSummary,
} from '../components/bet-builder-v3/BetBuilderV3Summary'
import {
  BB_V3_TABS,
  DEFAULT_BB_V3_FILTERS,
  PERIOD_OPTIONS,
  buildGroups,
  familyCounts,
  fixturesCovered,
  isPatternAgree,
  tally,
  uniqueSorted,
  type BbV3Filters,
  type BbV3Period,
  type BbV3Tab,
} from '../components/bet-builder-v3/bbV3Utils'
import { BetBuilderViewSwitch } from '../components/bet-builder/BetBuilderViewSwitch'
import {
  bbCard,
  bbChipActive,
  bbChipIdle,
  bbGridCards,
  bbMuted,
  bbPrimaryBtn,
  bbSecondaryBtn,
  bbSkeleton,
} from '../components/bet-builder/betBuilderStyles'
import type { BetBuilderPageView } from '../components/bet-builder/betBuilderResultsUtils'
import { formatDisplayDateIt, isIsoDate, shiftIsoDate } from '../components/bet-builder/betBuilderUtils'
import { fetchBetBuilderV3, type BbV3Response } from '../lib/cecchinoBetBuilderV3Api'
import { todayIsoRome } from '../lib/cecchinoTodayApi'
import { formatFetchError } from '../utils/formatFetchError'

const AVAILABLE_FROM = '2026-09-16'
const PAGE_SIZE = 12

function parseTab(v: string | null): BbV3Tab {
  return v === 'V3' || v === 'combo' ? v : 'V2.5'
}

function parsePeriod(v: string | null): BbV3Period {
  return v === 'yesterday' || v === 'last7' || v === 'all' ? v : 'today'
}

function periodRange(period: BbV3Period, today: string): { from: string; to: string } {
  if (period === 'yesterday') {
    const y = shiftIsoDate(today, -1)
    return { from: y, to: y }
  }
  if (period === 'last7') return { from: shiftIsoDate(today, -6), to: today }
  if (period === 'all') return { from: AVAILABLE_FROM, to: today }
  return { from: today, to: today }
}

const TAB_HINT: Record<BbV3Tab, string> = {
  'V2.5': 'Predizioni dell’Indice di Acquistabilità V2.5 (punteggio da 70 in su).',
  V3: 'Predizioni dell’Indice di Acquistabilità V3 (punteggio da 70 in su). La V3 analizza solo le partite con tiri e tiri in porta disponibili.',
  combo: 'Solo i mercati che V2.5 e V3 predicono entrambe (da 70 in su), senza pattern dei due modelli in contrasto.',
}

export function BetBuilderV3Page() {
  const [params, setParams] = useSearchParams()
  const today = todayIsoRome()
  const tab = parseTab(params.get('tab'))
  const view: BetBuilderPageView = params.get('view') === 'results' ? 'results' : 'pre-match'
  const dateParam = params.get('date')
  const date = isIsoDate(dateParam) ? dateParam : today
  const period = parsePeriod(params.get('period'))
  const range = view === 'results' ? periodRange(period, today) : { from: date, to: date }

  const [data, setData] = useState<BbV3Response | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<BbV3Filters>(DEFAULT_BB_V3_FILTERS)
  const [secondaryOpen, setSecondaryOpen] = useState(false)
  const [visible, setVisible] = useState(PAGE_SIZE)

  const setParam = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v == null) next.delete(k)
      else next.set(k, v)
    }
    setParams(next, { replace: true })
    setVisible(PAGE_SIZE)
  }

  const load = useCallback(async (from: string, to: string) => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchBetBuilderV3({ date_from: from, date_to: to }))
    } catch (e) {
      setError(formatFetchError(e))
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- sync URL → dati
    void load(range.from, range.to)
  }, [load, range.from, range.to])

  const items = useMemo(() => data?.fixtures ?? [], [data])
  const showOutcome = view === 'results'
  const effectiveFilters = useMemo(
    () => (showOutcome ? filters : { ...filters, outcome: 'all' as const }),
    [filters, showOutcome],
  )
  const groups = useMemo(() => buildGroups(items, tab, effectiveFilters), [items, tab, effectiveFilters])
  const counts = useMemo(() => familyCounts(items, tab, effectiveFilters), [items, tab, effectiveFilters])
  const totals = useMemo(() => tally(groups), [groups])
  const confirmed = useMemo(
    () => groups.reduce((n, g) => n + g.opportunities.filter(isPatternAgree).length, 0),
    [groups],
  )
  const covered = useMemo(() => fixturesCovered(items, tab), [items, tab])
  const countries = useMemo(() => uniqueSorted(items.map((i) => i.fixture.country)), [items])
  const leagues = useMemo(
    () =>
      uniqueSorted(
        items.filter((i) => !filters.country || i.fixture.country === filters.country).map((i) => i.fixture.league),
      ),
    [items, filters.country],
  )

  const onFiltersChange = (patch: Partial<BbV3Filters>) => {
    setFilters((prev) => ({ ...prev, ...patch }))
    setVisible(PAGE_SIZE)
  }

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-3 overflow-x-hidden pb-24 sm:space-y-4 md:pb-20">
      <header className="space-y-3" data-testid="bb-v3-header">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
          <div className="min-w-0 space-y-1">
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">Bet Builder V3</h1>
            {showOutcome ? (
              <>
                <p className="text-sm font-medium text-slate-700">Monitoraggio risultati</p>
                <p className="text-xs text-slate-500">
                  Esito delle opportunità consigliate. Disponibile dal 16/09/2026.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium capitalize text-slate-600 sm:hidden">{formatDisplayDateIt(date)}</p>
                <p className={`${bbMuted} text-xs sm:text-sm`}>
                  <span className="tabular-nums">{covered} partite analizzate</span>
                  {' · '}
                  <span className="tabular-nums">{groups.length} partite con opportunità</span>
                  {' · '}
                  <span className="tabular-nums">{totals.opportunities} opportunità</span>
                </p>
              </>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:flex-col sm:items-end sm:gap-2">
            <BetBuilderViewSwitch
              view={view}
              onChange={(v) => setParam({ view: v === 'results' ? 'results' : null })}
            />
            {!showOutcome ? (
              <div
                className="inline-flex items-stretch overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
                role="group"
                aria-label="Selezione giorno"
              >
                <button
                  type="button"
                  className="inline-flex min-h-10 min-w-10 items-center justify-center border-r border-slate-200 text-slate-700 transition hover:bg-slate-50"
                  aria-label="Giorno precedente"
                  onClick={() => setParam({ date: shiftIsoDate(date, -1) })}
                >
                  ←
                </button>
                <label className="relative flex min-h-10 min-w-[9.5rem] flex-1 cursor-pointer items-center justify-center px-2 sm:min-w-[11.5rem]">
                  <span className="pointer-events-none hidden text-sm font-semibold capitalize text-slate-900 sm:inline" aria-hidden>
                    {formatDisplayDateIt(date)}
                  </span>
                  <span className="pointer-events-none text-sm font-semibold text-slate-800 sm:hidden" aria-hidden>
                    Cambia data
                  </span>
                  <input
                    type="date"
                    className="absolute inset-0 cursor-pointer opacity-0"
                    value={date}
                    aria-label="Cambia data"
                    onChange={(e) => e.target.value && setParam({ date: e.target.value })}
                  />
                </label>
                <button
                  type="button"
                  className="inline-flex min-h-10 min-w-10 items-center justify-center border-l border-slate-200 text-slate-700 transition hover:bg-slate-50"
                  aria-label="Giorno successivo"
                  onClick={() => setParam({ date: shiftIsoDate(date, 1) })}
                >
                  →
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2" role="group" aria-label="Periodo">
                {PERIOD_OPTIONS.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    aria-pressed={period === p.key}
                    className={`${period === p.key ? bbChipActive : bbChipIdle} min-h-9 py-1.5`}
                    onClick={() => setParam({ period: p.key === 'today' ? null : p.key })}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div
          className="inline-flex overflow-hidden rounded-xl border border-slate-200 bg-slate-100/80 p-1 shadow-sm"
          role="tablist"
          aria-label="Modello"
          data-testid="bb-v3-model-tabs"
        >
          {BB_V3_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              className={`min-h-10 rounded-lg px-4 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
                tab === t.key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
              }`}
              onClick={() => setParam({ tab: t.key === 'V2.5' ? null : t.key })}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p className="text-sm text-slate-600">{TAB_HINT[tab]}</p>
      </header>

      {loading ? (
        <div className={bbGridCards} aria-busy="true" data-testid="bb-v3-loading">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className={`${bbSkeleton} space-y-3 p-4`}>
              <div className="h-3 w-32 rounded bg-slate-300/80" />
              <div className="flex items-center justify-between gap-4">
                <div className="h-12 w-12 rounded-full bg-slate-300/80" />
                <div className="h-4 w-20 rounded bg-slate-300/60" />
                <div className="h-12 w-12 rounded-full bg-slate-300/80" />
              </div>
              <div className="h-28 rounded-2xl bg-slate-300/60" />
            </div>
          ))}
        </div>
      ) : null}

      {!loading && error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-900" role="alert">
          <p className="font-medium">{error}</p>
          <button type="button" className={`${bbPrimaryBtn} mt-3`} onClick={() => void load(range.from, range.to)}>
            Riprova
          </button>
        </div>
      ) : null}

      {!loading && !error && data ? (
        <>
          {showOutcome ? (
            <BetBuilderV3ResultsSummary tally={totals} />
          ) : (
            <BetBuilderV3PrematchSummary
              fixtures={covered}
              fixturesWithOpportunity={groups.length}
              tally={totals}
              confirmed={confirmed}
            />
          )}

          <BetBuilderV3Filters
            filters={filters}
            counts={counts}
            countries={countries}
            leagues={leagues}
            tab={tab}
            showOutcome={showOutcome}
            secondaryOpen={secondaryOpen}
            onToggleSecondary={() => setSecondaryOpen((v) => !v)}
            onChange={onFiltersChange}
          />

          {groups.length === 0 ? (
            <div className={`${bbCard} border-dashed px-4 py-10 text-center`} data-testid="bb-v3-empty">
              <p className="text-base font-semibold text-slate-800">
                {items.length ? 'Nessuna opportunità con i filtri attuali' : 'Nessuna partita registrata per questo periodo'}
              </p>
              <p className="mt-1 text-sm text-slate-500">
                {items.length
                  ? 'Prova ad allentare mercato, pattern o giocabilità.'
                  : 'Le predizioni arrivano con la scansione del mattino (disponibili dal 16/09/2026).'}
              </p>
            </div>
          ) : (
            <>
              <p className="text-sm text-slate-600">
                {groups.length} {groups.length === 1 ? 'partita' : 'partite'} · {totals.opportunities} opportunità
              </p>
              <div className={bbGridCards} data-testid="bb-v3-cards">
                {groups.slice(0, visible).map((g) => (
                  <BetBuilderV3FixtureCard
                    key={`${tab}-${g.fixture.today_fixture_id}`}
                    group={g}
                    tab={tab}
                    showOutcome={showOutcome}
                  />
                ))}
              </div>
              {visible < groups.length ? (
                <div className="flex justify-center">
                  <button type="button" className={bbSecondaryBtn} onClick={() => setVisible((n) => n + PAGE_SIZE)}>
                    Mostra altre ({groups.length - visible} rimanenti)
                  </button>
                </div>
              ) : null}
            </>
          )}
        </>
      ) : null}
    </div>
  )
}
