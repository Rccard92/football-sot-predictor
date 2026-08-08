import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { BetBuilderFilters } from '../components/bet-builder/BetBuilderFilters'
import { BetBuilderFixtureCard } from '../components/bet-builder/BetBuilderFixtureCard'
import { BetBuilderHeader } from '../components/bet-builder/BetBuilderHeader'
import { BetBuilderResultDetailDrawer } from '../components/bet-builder/BetBuilderResultDetailDrawer'
import { BetBuilderResultFixtureCard } from '../components/bet-builder/BetBuilderResultFixtureCard'
import { BetBuilderResultsFilters } from '../components/bet-builder/BetBuilderResultsFilters'
import { BetBuilderResultsSummary } from '../components/bet-builder/BetBuilderResultsSummary'
import { BetBuilderSummary } from '../components/bet-builder/BetBuilderSummary'
import {
  bbCard,
  bbGridCards,
  bbPrimaryBtn,
  bbSecondaryBtn,
  bbSkeleton,
} from '../components/bet-builder/betBuilderStyles'
import {
  BET_BUILDER_RESULTS_POLL_ACTIVE_MS,
  BET_BUILDER_RESULTS_POLL_SETTLED_MS,
  applyResultsFiltersPatch,
  clampResultsDate,
  defaultResultsFilters,
  mapResultsQuickFilterToApi,
  parseBetBuilderView,
  resultsNeedActivePolling,
  type BetBuilderPageView,
  type BetBuilderResultsFilterState,
} from '../components/bet-builder/betBuilderResultsUtils'
import {
  BET_BUILDER_PAGE_SIZE,
  BET_BUILDER_POLL_IDLE_MS,
  BET_BUILDER_POLL_RUNNING_MS,
  DEFAULT_BET_BUILDER_FILTERS,
  buildBetBuilderFixtureGroups,
  countFilteredOpportunities,
  countUniqueFixtures,
  isIsoDate,
  isScanRunning,
  nextVisibleLimit,
  resolveLastUpdatedIso,
  sliceProgressive,
  uniqueSorted,
  type BetBuilderFilterState,
  type BetBuilderViewMode,
} from '../components/bet-builder/betBuilderUtils'
import { BetBuilderCartButton } from '../components/bet-builder/cart/BetBuilderCartButton'
import { BetBuilderCartDrawer } from '../components/bet-builder/cart/BetBuilderCartDrawer'
import { useBetBuilderCart } from '../components/bet-builder/cart/useBetBuilderCart'
import {
  BET_BUILDER_RESULTS_START_DATE,
  fetchBetBuilderOpportunities,
  fetchBetBuilderResults,
  type BetBuilderOpportunitiesResponse,
  type BetBuilderOpportunity,
  type BetBuilderResultsFixture,
  type BetBuilderResultsResponse,
} from '../lib/cecchinoBetBuilderApi'
import { todayIsoRome } from '../lib/cecchinoTodayApi'
import { formatFetchError } from '../utils/formatFetchError'

export function BetBuilderPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const dateParam = searchParams.get('date')
  const viewParam = searchParams.get('view')
  const view = parseBetBuilderView(viewParam)
  const today = todayIsoRome()
  const selectedDate = isIsoDate(dateParam)
    ? view === 'results'
      ? clampResultsDate(dateParam, today)
      : dateParam
    : today

  const [data, setData] = useState<BetBuilderOpportunitiesResponse | null>(null)
  const [resultsData, setResultsData] = useState<BetBuilderResultsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<BetBuilderFilterState>(DEFAULT_BET_BUILDER_FILTERS)
  const [resultsFilters, setResultsFilters] = useState<BetBuilderResultsFilterState>(() =>
    defaultResultsFilters(today),
  )
  const [resultsFiltersOpen, setResultsFiltersOpen] = useState(false)
  const [secondaryOpen, setSecondaryOpen] = useState(false)
  const [visibleLimit, setVisibleLimit] = useState(BET_BUILDER_PAGE_SIZE)
  const [viewMode, setViewMode] = useState<BetBuilderViewMode>('compact')
  const [detailItem, setDetailItem] = useState<BetBuilderResultsFixture | null>(null)

  const revisionRef = useRef<string | null>(null)
  const dateRef = useRef(selectedDate)
  const viewRef = useRef(view)
  const resultsFiltersRef = useRef(resultsFilters)
  const pendingSortAutoRef = useRef(false)
  const inFlightRef = useRef(false)

  useEffect(() => {
    dateRef.current = selectedDate
  }, [selectedDate])

  useEffect(() => {
    viewRef.current = view
  }, [view])

  useEffect(() => {
    resultsFiltersRef.current = resultsFilters
  }, [resultsFilters])

  useEffect(() => {
    if (view === 'results') {
      const day = clampResultsDate(
        isIsoDate(dateParam) ? dateParam : today,
        today,
      )
      if (!isIsoDate(dateParam) || dateParam < BET_BUILDER_RESULTS_START_DATE || viewParam !== 'results') {
        setSearchParams({ date: day, view: 'results' }, { replace: true })
      }
      return
    }
    if (!isIsoDate(dateParam) || (viewParam != null && viewParam !== 'pre-match')) {
      const next: Record<string, string> = { date: selectedDate }
      setSearchParams(next, { replace: true })
    }
  }, [dateParam, selectedDate, setSearchParams, today, view, viewParam])

  const setView = useCallback(
    (next: BetBuilderPageView) => {
      if (next === 'results') {
        const day = clampResultsDate(selectedDate, today)
        setResultsFilters((prev) => ({
          ...prev,
          dateFrom: day,
          dateTo: day,
        }))
        setSearchParams({ date: day, view: 'results' }, { replace: true })
      } else {
        setSearchParams({ date: selectedDate }, { replace: true })
      }
      setError(null)
      setDetailItem(null)
    },
    [selectedDate, setSearchParams, today],
  )

  const setDate = useCallback(
    (next: string) => {
      if (!isIsoDate(next)) return
      setSearchParams({ date: next }, { replace: true })
      setFilters(DEFAULT_BET_BUILDER_FILTERS)
      setVisibleLimit(BET_BUILDER_PAGE_SIZE)
      revisionRef.current = null
    },
    [setSearchParams],
  )

  const applyResponse = useCallback((payload: BetBuilderOpportunitiesResponse, soft: boolean) => {
    const prevRevision = revisionRef.current
    const changed = prevRevision != null && prevRevision !== payload.source_revision
    revisionRef.current = payload.source_revision
    setData(payload)
    setError(null)
    if (soft && changed) {
      toast.success('Dati Bet Builder aggiornati', {
        description: 'Nuova scansione Cecchino ricevuta',
      })
    }
  }, [])

  const loadPrematch = useCallback(
    async (opts?: { soft?: boolean; date?: string }) => {
      const date = opts?.date ?? dateRef.current
      const soft = Boolean(opts?.soft)
      if (inFlightRef.current && soft) return
      inFlightRef.current = true
      if (!soft) {
        setLoading(true)
        setError(null)
      }
      try {
        const payload = await fetchBetBuilderOpportunities({ date })
        if (date !== dateRef.current || viewRef.current !== 'pre-match') return
        applyResponse(payload, soft)
      } catch (e) {
        if (date !== dateRef.current || viewRef.current !== 'pre-match') return
        if (!soft) {
          setError(formatFetchError(e))
          setData(null)
        }
      } finally {
        inFlightRef.current = false
        if (!soft) setLoading(false)
      }
    },
    [applyResponse],
  )

  const loadResults = useCallback(async (opts?: { soft?: boolean }) => {
    const soft = Boolean(opts?.soft)
    const rf = resultsFiltersRef.current
    if (inFlightRef.current && soft) return
    inFlightRef.current = true
    if (!soft) {
      setLoading(true)
      setError(null)
    }
    try {
      const dateFrom = clampResultsDate(rf.dateFrom, todayIsoRome())
      const dateTo = clampResultsDate(rf.dateTo, todayIsoRome())
      const quick = mapResultsQuickFilterToApi(rf.outcome)
      const payload = await fetchBetBuilderResults({
        date_from: dateFrom,
        date_to: dateTo,
        outcome: quick.outcome,
        match_status: quick.match_status,
        market_key: rf.market !== 'all' ? rf.market : undefined,
        origin: rf.origin !== 'all' ? rf.origin : undefined,
        min_purchasability: rf.minPurchasability ?? undefined,
        sort: rf.sort,
        limit: 50,
        offset: 0,
      })
      if (viewRef.current !== 'results') return
      setResultsData(payload)
      setError(null)
    } catch (e) {
      if (viewRef.current !== 'results') return
      if (!soft) {
        setError(formatFetchError(e))
        setResultsData(null)
      }
    } finally {
      inFlightRef.current = false
      if (!soft) setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (view === 'pre-match') {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync URL date → remote opportunities
      void loadPrematch({ date: selectedDate })
    }
  }, [selectedDate, view, loadPrematch])

  useEffect(() => {
    if (view === 'results') {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync filters → results
      void loadResults()
    }
  }, [view, resultsFilters, loadResults])

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      if (viewRef.current === 'results') void loadResults({ soft: true })
      else void loadPrematch({ soft: true })
    }
    const onFocus = () => {
      if (viewRef.current === 'results') void loadResults({ soft: true })
      else void loadPrematch({ soft: true })
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onFocus)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onFocus)
    }
  }, [loadPrematch, loadResults])

  useEffect(() => {
    if (view !== 'pre-match') return
    const running = isScanRunning(data?.source_scan_status)
    const ms = running ? BET_BUILDER_POLL_RUNNING_MS : BET_BUILDER_POLL_IDLE_MS
    const id = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      void loadPrematch({ soft: true })
    }, ms)
    return () => window.clearInterval(id)
  }, [data?.source_scan_status, loadPrematch, view])

  useEffect(() => {
    if (view !== 'results') return
    const active = resultsNeedActivePolling(resultsData?.fixtures)
    const ms = active ? BET_BUILDER_RESULTS_POLL_ACTIVE_MS : BET_BUILDER_RESULTS_POLL_SETTLED_MS
    const id = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      void loadResults({ soft: true })
    }, ms)
    return () => window.clearInterval(id)
  }, [loadResults, resultsData?.fixtures, view])

  const onFiltersChange = useCallback((patch: Partial<BetBuilderFilterState>) => {
    setFilters((prev) => ({ ...prev, ...patch }))
    setVisibleLimit(BET_BUILDER_PAGE_SIZE)
  }, [])

  const onResultsFiltersChange = useCallback((patch: Partial<BetBuilderResultsFilterState>) => {
    setResultsFilters((prev) => {
      const { filters: next, pendingSortAuto } = applyResultsFiltersPatch(
        prev,
        patch,
        pendingSortAutoRef.current,
        todayIsoRome(),
      )
      pendingSortAutoRef.current = pendingSortAuto
      return next
    })
  }, [])

  const filterLost = useCallback(() => {
    setResultsFilters((prev) => ({ ...prev, outcome: 'lost' }))
  }, [])

  // Cart riconcilia contro opportunities COMPLETE — mai contro filtered.
  const cart = useBetBuilderCart({
    date: selectedDate,
    opportunities: data?.opportunities ?? [],
    sourceRevision: data?.source_revision ?? null,
  })

  const cartOpportunityKeys = useMemo(
    () => new Set(cart.cart.items.map((i) => i.opportunity_key)),
    [cart.cart.items],
  )

  const groups = useMemo(
    () => buildBetBuilderFixtureGroups(data?.opportunities ?? [], filters),
    [data?.opportunities, filters],
  )

  const visible = useMemo(
    () => sliceProgressive(groups, visibleLimit),
    [groups, visibleLimit],
  )

  const fixturesWithOpportunity = useMemo(
    () => countUniqueFixtures(data?.opportunities ?? []),
    [data?.opportunities],
  )

  const filteredOpportunityCount = useMemo(
    () => countFilteredOpportunities(groups),
    [groups],
  )

  const countries = useMemo(
    () => uniqueSorted((data?.opportunities ?? []).map((o) => o.fixture.country)),
    [data?.opportunities],
  )

  const leagues = useMemo(() => {
    const source = (data?.opportunities ?? []).filter(
      (o) => !filters.country || o.fixture.country === filters.country,
    )
    return uniqueSorted(source.map((o) => o.fixture.league))
  }, [data?.opportunities, filters.country])

  const lastUpdated = resolveLastUpdatedIso(data?.freshness, data?.source_generated_from)
  const hasRawOpportunities = (data?.opportunities.length ?? 0) > 0
  const filtersRestrictive = hasRawOpportunities && groups.length === 0
  const eligible =
    typeof data?.summary.fixtures_eligible_total === 'number'
      ? data.summary.fixtures_eligible_total
      : data?.summary.fixtures_considered

  const resultsFixtures = resultsData?.fixtures ?? []

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-3 overflow-x-hidden pb-24 sm:space-y-4 md:pb-20">
      <BetBuilderHeader
        date={selectedDate}
        onDateChange={setDate}
        view={view}
        onViewChange={setView}
        sourceScanStatus={data?.source_scan_status ?? data?.freshness?.source_scan_status}
        lastUpdatedIso={lastUpdated}
        freshnessWarning={data?.freshness?.freshness_warning}
        fixturesEligible={eligible}
        fixturesWithOpportunity={data ? fixturesWithOpportunity : undefined}
        opportunitiesTotal={data?.summary.opportunities_total}
        hideDateNav={view === 'results'}
      />

      {loading ? (
        <div
          className={bbGridCards}
          aria-busy="true"
          aria-live="polite"
          data-testid="bet-builder-loading"
        >
          <span className="sr-only">Caricamento Bet Builder</span>
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className={`${bbSkeleton} space-y-3 p-4`} data-testid="bet-builder-skeleton">
              <div className="flex justify-between">
                <div className="h-3 w-32 rounded bg-slate-300/80" />
                <div className="h-6 w-14 rounded bg-slate-300/80" />
              </div>
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
        <div
          className="rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-900"
          role="alert"
          data-testid="bet-builder-error"
        >
          <p className="font-medium">{error}</p>
          <button
            type="button"
            className={`${bbPrimaryBtn} mt-3`}
            onClick={() =>
              view === 'results' ? void loadResults() : void loadPrematch()
            }
          >
            Riprova
          </button>
        </div>
      ) : null}

      {!loading && !error && view === 'results' && resultsData ? (
        <>
          <BetBuilderResultsSummary summary={resultsData.summary} onFilterLost={filterLost} />
          <BetBuilderResultsFilters
            filters={resultsFilters}
            onChange={onResultsFiltersChange}
            filtersOpen={resultsFiltersOpen}
            onFiltersOpenChange={setResultsFiltersOpen}
          />
          {resultsFixtures.length === 0 ? (
            <div
              className={`${bbCard} border-dashed px-4 py-10 text-center`}
              data-testid="bet-builder-results-empty"
            >
              <p className="text-base font-semibold text-slate-800">
                Nessuna prediction nel periodo
              </p>
              <p className="mt-1 text-sm text-slate-500">
                Monitoraggio disponibile dall&apos;08/08/2026. Prova ad allentare i filtri.
              </p>
            </div>
          ) : (
            <div className={bbGridCards} data-testid="bet-builder-results-cards">
              {resultsFixtures.map((item) => (
                <BetBuilderResultFixtureCard
                  key={item.fixture.today_fixture_id}
                  item={item}
                  onOpenDetail={setDetailItem}
                />
              ))}
            </div>
          )}
          <BetBuilderResultDetailDrawer
            open={detailItem != null}
            item={detailItem}
            onClose={() => setDetailItem(null)}
          />
        </>
      ) : null}

      {!loading && !error && view === 'pre-match' && data ? (
        <>
          <BetBuilderSummary
            summary={data.summary}
            fixturesWithOpportunity={fixturesWithOpportunity}
          />
          <BetBuilderFilters
            filters={filters}
            byMarket={data.summary.by_market ?? {}}
            countries={countries}
            leagues={leagues}
            secondaryOpen={secondaryOpen}
            onToggleSecondary={() => setSecondaryOpen((v) => !v)}
            onChange={onFiltersChange}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
          />

          {groups.length === 0 ? (
            <div
              className={`${bbCard} border-dashed px-4 py-10 text-center`}
              data-testid="bet-builder-empty"
            >
              {filtersRestrictive ? (
                <>
                  <p className="text-base font-semibold text-slate-800">
                    Nessuna opportunity con i filtri attuali
                  </p>
                  <p className="mt-1 text-sm text-slate-500">
                    Prova ad allentare mercato, origine o soglia Acquistabilità.
                  </p>
                </>
              ) : (
                <>
                  <p className="text-base font-semibold text-slate-800">
                    Nessuna opportunity per questa giornata
                  </p>
                  <p className="mt-1 text-sm text-slate-500">
                    Non risultano opportunity PRICE_VALUE o SIGNAL_VALUE per la data selezionata.
                  </p>
                </>
              )}
            </div>
          ) : (
            <>
              <p
                className="text-sm text-slate-600"
                data-testid="bet-builder-filtered-counts"
              >
                {groups.length} {groups.length === 1 ? 'partita' : 'partite'} ·{' '}
                {filteredOpportunityCount}{' '}
                {filteredOpportunityCount === 1 ? 'opportunity' : 'opportunity'}
              </p>
              <div className={bbGridCards} data-testid="bet-builder-cards">
                {visible.map((group) => (
                  <BetBuilderFixtureCard
                    key={group.todayFixtureId}
                    group={group}
                    scanDate={data.scan_date || selectedDate}
                    viewMode={viewMode}
                    cart={{
                      getCtaFor: cart.getCtaFor,
                      cartOpportunityKeys,
                      fixtureCartLabel: cart.fixtureCartLabel(group.todayFixtureId),
                      onAdd: cart.add,
                      onReplace: cart.replace,
                      onRemove: (opportunity: BetBuilderOpportunity) => {
                        cart.remove({
                          today_fixture_id: opportunity.fixture.today_fixture_id,
                          opportunity_key: opportunity.opportunity_key,
                        })
                      },
                    }}
                  />
                ))}
              </div>
              {visibleLimit < groups.length ? (
                <div className="flex justify-center">
                  <button
                    type="button"
                    className={bbSecondaryBtn}
                    data-testid="bet-builder-show-more"
                    onClick={() =>
                      setVisibleLimit((n) => nextVisibleLimit(n, groups.length))
                    }
                  >
                    Mostra altre ({groups.length - visibleLimit} rimanenti)
                  </button>
                </div>
              ) : null}
            </>
          )}
        </>
      ) : null}

      {view === 'pre-match' ? (
        <>
          <BetBuilderCartButton
            selectionCount={cart.selectionCount}
            combinedOdds={cart.combinedOdds}
            onOpen={() => cart.setOpen(true)}
          />
          <BetBuilderCartDrawer
            open={cart.isOpen}
            onClose={() => cart.setOpen(false)}
            date={selectedDate}
            items={cart.resolvedItems}
            combinedOdds={cart.combinedOdds}
            onRemove={cart.remove}
            onClear={cart.clear}
          />
        </>
      ) : null}
    </div>
  )
}
