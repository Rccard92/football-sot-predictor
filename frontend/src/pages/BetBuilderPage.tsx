import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BetBuilderFilters } from '../components/bet-builder/BetBuilderFilters'
import { BetBuilderFixtureCard } from '../components/bet-builder/BetBuilderFixtureCard'
import { BetBuilderHeader } from '../components/bet-builder/BetBuilderHeader'
import { BetBuilderSummary } from '../components/bet-builder/BetBuilderSummary'
import {
  bbCard,
  bbGridCards,
  bbPrimaryBtn,
  bbSecondaryBtn,
  bbSkeleton,
} from '../components/bet-builder/betBuilderStyles'
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
} from '../components/bet-builder/betBuilderUtils'
import {
  fetchBetBuilderOpportunities,
  type BetBuilderOpportunitiesResponse,
} from '../lib/cecchinoBetBuilderApi'
import { todayIsoRome } from '../lib/cecchinoTodayApi'
import { formatFetchError } from '../utils/formatFetchError'

export function BetBuilderPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const dateParam = searchParams.get('date')
  const selectedDate = isIsoDate(dateParam) ? dateParam : todayIsoRome()

  const [data, setData] = useState<BetBuilderOpportunitiesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<BetBuilderFilterState>(DEFAULT_BET_BUILDER_FILTERS)
  const [secondaryOpen, setSecondaryOpen] = useState(false)
  const [visibleLimit, setVisibleLimit] = useState(BET_BUILDER_PAGE_SIZE)
  const [revisionBanner, setRevisionBanner] = useState(false)

  const revisionRef = useRef<string | null>(null)
  const dateRef = useRef(selectedDate)
  const bannerTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inFlightRef = useRef(false)

  useEffect(() => {
    dateRef.current = selectedDate
  }, [selectedDate])

  useEffect(() => {
    if (!isIsoDate(dateParam)) {
      setSearchParams({ date: selectedDate }, { replace: true })
    }
  }, [dateParam, selectedDate, setSearchParams])

  const setDate = useCallback(
    (next: string) => {
      if (!isIsoDate(next)) return
      setSearchParams({ date: next }, { replace: true })
      setFilters(DEFAULT_BET_BUILDER_FILTERS)
      setVisibleLimit(BET_BUILDER_PAGE_SIZE)
      setRevisionBanner(false)
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
      setRevisionBanner(true)
      if (bannerTimerRef.current) clearTimeout(bannerTimerRef.current)
      bannerTimerRef.current = setTimeout(() => setRevisionBanner(false), 5000)
    }
  }, [])

  const load = useCallback(
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
        if (date !== dateRef.current) return
        applyResponse(payload, soft)
      } catch (e) {
        if (date !== dateRef.current) return
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

  useEffect(() => {
    // Fetch giornata selezionata: setState asincrono via load (pattern data-fetch).
    // eslint-disable-next-line react-hooks/set-state-in-effect -- sync URL date → remote opportunities
    void load({ date: selectedDate })
  }, [selectedDate, load])

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        void load({ soft: true })
      }
    }
    const onFocus = () => {
      void load({ soft: true })
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onFocus)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onFocus)
    }
  }, [load])

  useEffect(() => {
    const running = isScanRunning(data?.source_scan_status)
    const ms = running ? BET_BUILDER_POLL_RUNNING_MS : BET_BUILDER_POLL_IDLE_MS
    const id = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      void load({ soft: true })
    }, ms)
    return () => window.clearInterval(id)
  }, [data?.source_scan_status, load])

  useEffect(() => {
    return () => {
      if (bannerTimerRef.current) clearTimeout(bannerTimerRef.current)
    }
  }, [])

  const onFiltersChange = useCallback((patch: Partial<BetBuilderFilterState>) => {
    setFilters((prev) => ({ ...prev, ...patch }))
    setVisibleLimit(BET_BUILDER_PAGE_SIZE)
  }, [])

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

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-6 overflow-x-hidden">
      <BetBuilderHeader
        date={selectedDate}
        onDateChange={setDate}
        sourceScanStatus={data?.source_scan_status ?? data?.freshness?.source_scan_status}
        lastUpdatedIso={lastUpdated}
        freshnessWarning={data?.freshness?.freshness_warning}
        revisionUpdatedBanner={revisionBanner}
      />

      {loading ? (
        <div
          className={bbGridCards}
          aria-busy="true"
          aria-live="polite"
          data-testid="bet-builder-loading"
        >
          <span className="sr-only">Caricamento opportunity Bet Builder</span>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className={`${bbSkeleton} h-64`} />
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
            onClick={() => void load()}
          >
            Riprova
          </button>
        </div>
      ) : null}

      {!loading && !error && data ? (
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
    </div>
  )
}
