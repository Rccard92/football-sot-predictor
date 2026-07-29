import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { CecchinoLabShell } from '../components/cecchino-data-lab/CecchinoLabShell'
import { HistoricalRunBalance } from '../components/cecchino-data-lab/historical-run/HistoricalRunBalance'
import { HistoricalRunCompetitions } from '../components/cecchino-data-lab/historical-run/HistoricalRunCompetitions'
import { HistoricalRunExclusions } from '../components/cecchino-data-lab/historical-run/HistoricalRunExclusions'
import { HistoricalRunFilterBar } from '../components/cecchino-data-lab/historical-run/HistoricalRunFilterBar'
import { HistoricalRunGoalIntensity } from '../components/cecchino-data-lab/historical-run/HistoricalRunGoalIntensity'
import { HistoricalRunHeader } from '../components/cecchino-data-lab/historical-run/HistoricalRunHeader'
import { HistoricalRunLiveProgress } from '../components/cecchino-data-lab/historical-run/HistoricalRunLiveProgress'
import { HistoricalRunMarketOverview } from '../components/cecchino-data-lab/historical-run/HistoricalRunMarketOverview'
import { HistoricalRunMatchDetail } from '../components/cecchino-data-lab/historical-run/HistoricalRunMatchDetail'
import { HistoricalRunMatches } from '../components/cecchino-data-lab/historical-run/HistoricalRunMatches'
import { HistoricalRunModuleCoveragePanel } from '../components/cecchino-data-lab/historical-run/HistoricalRunModuleCoveragePanel'
import { HistoricalRunPatterns } from '../components/cecchino-data-lab/historical-run/HistoricalRunPatterns'
import { HistoricalRunPurchasability } from '../components/cecchino-data-lab/historical-run/HistoricalRunPurchasability'
import { HistoricalRunRatingHeatmap } from '../components/cecchino-data-lab/historical-run/HistoricalRunRatingHeatmap'
import { HistoricalRunSectionError } from '../components/cecchino-data-lab/historical-run/HistoricalRunSectionError'
import { HistoricalRunSignalModelsFromDashboard } from '../components/cecchino-data-lab/historical-run/HistoricalRunSignalModels'
import { HistoricalRunSkeleton } from '../components/cecchino-data-lab/historical-run/HistoricalRunSkeleton'
import { HistoricalRunTimeline } from '../components/cecchino-data-lab/historical-run/HistoricalRunTimeline'
import { HistoricalRunV1Pulse } from '../components/cecchino-data-lab/historical-run/HistoricalRunV1Pulse'
import {
  getHistoricalRunDashboardBalance,
  getHistoricalRunDashboardCompetitions,
  getHistoricalRunDashboardExclusions,
  getHistoricalRunDashboardGoalIntensity,
  getHistoricalRunDashboardMarkets,
  getHistoricalRunDashboardOverview,
  getHistoricalRunDashboardPatterns,
  getHistoricalRunDashboardPurchasability,
  getHistoricalRunDashboardRatings,
  getHistoricalRunDashboardSignals,
  getHistoricalRunDashboardTimeline,
  getHistoricalRunMatchDetail,
  isHistoricalScanActive,
  listHistoricalRunMatches,
  parseHistoricalRunFiltersFromSearch,
  type HistoricalRunBalanceAnalytics,
  type HistoricalRunCompetitionAnalytics,
  type HistoricalRunDashboardMarket,
  type HistoricalRunDashboardOverview,
  type HistoricalRunExclusion,
  type HistoricalRunFilters,
  type HistoricalRunGoalIntensityAnalytics,
  type HistoricalRunMatchDetail as MatchDetail,
  type HistoricalRunMatchRow,
  type HistoricalRunPattern,
  type HistoricalRunPurchasabilityAnalytics,
  type HistoricalRunRatingCell,
  type HistoricalRunSignalsDashboard,
  type HistoricalRunTimelinePoint,
} from '../lib/cecchinoLabApi'

type SectionState<T> = { data: T | null; error: string | null; loading: boolean }

function emptySection<T>(): SectionState<T> {
  return { data: null, error: null, loading: true }
}

export function CecchinoLabHistoricalRunPage() {
  const { runId: runIdParam } = useParams()
  const runId = Number(runIdParam)
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(
    () => parseHistoricalRunFiltersFromSearch(searchParams.toString()),
    [searchParams],
  )

  const [overview, setOverview] = useState<SectionState<HistoricalRunDashboardOverview>>(emptySection())
  const [markets, setMarkets] = useState<SectionState<HistoricalRunDashboardMarket[]>>(emptySection())
  const [ratings, setRatings] = useState<
    SectionState<{ bands: string[]; matrix: HistoricalRunRatingCell[]; warning?: string }>
  >(emptySection())
  const [purch, setPurch] = useState<SectionState<HistoricalRunPurchasabilityAnalytics>>(emptySection())
  const [signals, setSignals] = useState<SectionState<HistoricalRunSignalsDashboard>>(emptySection())
  const [balance, setBalance] = useState<SectionState<HistoricalRunBalanceAnalytics>>(emptySection())
  const [gi, setGi] = useState<SectionState<HistoricalRunGoalIntensityAnalytics>>(emptySection())
  const [comps, setComps] = useState<SectionState<HistoricalRunCompetitionAnalytics[]>>(emptySection())
  const [timeline, setTimeline] = useState<
    SectionState<{ points: HistoricalRunTimelinePoint[]; granularity: string }>
  >(emptySection())
  const [patterns, setPatterns] = useState<
    SectionState<{
      positive: HistoricalRunPattern[]
      negative: HistoricalRunPattern[]
      watchlist: HistoricalRunPattern[]
      unstable: HistoricalRunPattern[]
      diagnostics?: HistoricalRunPattern[]
    }>
  >(emptySection())
  const [exclusions, setExclusions] = useState<
    SectionState<{ items: HistoricalRunExclusion[]; total: number }>
  >(emptySection())
  const [matches, setMatches] = useState<
    SectionState<{ items: HistoricalRunMatchRow[]; total: number; offset: number; limit: number }>
  >(emptySection())
  const [matchOffset, setMatchOffset] = useState(0)
  const [granularity, setGranularity] = useState('week')
  const [detail, setDetail] = useState<MatchDetail | null>(null)
  const [lazyReady, setLazyReady] = useState(false)

  const setFilters = useCallback(
    (next: HistoricalRunFilters) => {
      const params = new URLSearchParams()
      for (const [k, v] of Object.entries(next)) {
        if (v != null && String(v).trim() !== '') params.set(k, String(v))
      }
      setSearchParams(params, { replace: true })
    },
    [setSearchParams],
  )

  const loadCore = useCallback(async () => {
    if (!Number.isFinite(runId)) return
    try {
      const ov = await getHistoricalRunDashboardOverview(runId, filters)
      setOverview({ data: ov, error: null, loading: false })
    } catch (e) {
      setOverview({
        data: null,
        error: e instanceof Error ? e.message : 'Errore overview',
        loading: false,
      })
    }

    const load = async <T,>(
      fn: () => Promise<T>,
      setter: (s: SectionState<T>) => void,
    ) => {
      try {
        const data = await fn()
        setter({ data, error: null, loading: false })
      } catch (e) {
        setter({
          data: null,
          error: e instanceof Error ? e.message : 'Errore sezione',
          loading: false,
        })
      }
    }

    await Promise.all([
      load(async () => (await getHistoricalRunDashboardMarkets(runId, filters)).markets, setMarkets),
      load(async () => {
        const r = await getHistoricalRunDashboardRatings(runId, filters)
        return { bands: r.bands, matrix: r.matrix, warning: r.warning }
      }, setRatings),
      load(() => getHistoricalRunDashboardPurchasability(runId, filters), setPurch),
      load(() => getHistoricalRunDashboardSignals(runId, filters), setSignals),
      load(() => getHistoricalRunDashboardBalance(runId, filters), setBalance),
      load(() => getHistoricalRunDashboardGoalIntensity(runId, filters), setGi),
      load(
        async () => (await getHistoricalRunDashboardCompetitions(runId, filters)).competitions,
        setComps,
      ),
      load(async () => {
        const m = await listHistoricalRunMatches(runId, filters, {
          limit: 50,
          offset: matchOffset,
        })
        return { items: m.items, total: m.total, offset: m.offset, limit: m.limit }
      }, setMatches),
    ])
  }, [runId, filters, matchOffset])

  const loadLazy = useCallback(async () => {
    if (!Number.isFinite(runId)) return
    try {
      const t = await getHistoricalRunDashboardTimeline(runId, filters, { granularity })
      setTimeline({
        data: { points: t.points, granularity: t.granularity },
        error: null,
        loading: false,
      })
    } catch (e) {
      setTimeline({
        data: null,
        error: e instanceof Error ? e.message : 'Errore timeline',
        loading: false,
      })
    }
    try {
      const p = await getHistoricalRunDashboardPatterns(runId, filters)
      setPatterns({
        data: {
          positive: p.positive,
          negative: p.negative,
          watchlist: p.watchlist,
          unstable: p.unstable,
          diagnostics: p.diagnostics ?? [],
        },
        error: null,
        loading: false,
      })
    } catch (e) {
      setPatterns({
        data: null,
        error: e instanceof Error ? e.message : 'Errore pattern',
        loading: false,
      })
    }
    try {
      const ex = await getHistoricalRunDashboardExclusions(runId, filters)
      setExclusions({
        data: { items: ex.items, total: ex.total_excluded },
        error: null,
        loading: false,
      })
    } catch (e) {
      setExclusions({
        data: null,
        error: e instanceof Error ? e.message : 'Errore esclusioni',
        loading: false,
      })
    }
  }, [runId, filters, granularity])

  useEffect(() => {
    void loadCore()
  }, [loadCore])

  useEffect(() => {
    if (!lazyReady) {
      const t = window.setTimeout(() => setLazyReady(true), 400)
      return () => window.clearTimeout(t)
    }
    void loadLazy()
  }, [lazyReady, loadLazy])

  // Polling run attivo
  useEffect(() => {
    const status = overview.data?.run.status
    if (!status || !isHistoricalScanActive(status)) return
    const id = window.setInterval(() => {
      void loadCore()
    }, 4000)
    const id2 = window.setInterval(() => {
      if (lazyReady) void loadLazy()
    }, 20000)
    return () => {
      window.clearInterval(id)
      window.clearInterval(id2)
    }
  }, [overview.data?.run.status, loadCore, loadLazy, lazyReady])

  async function openMatch(snapshotId: number) {
    try {
      const d = await getHistoricalRunMatchDetail(runId, snapshotId)
      setDetail(d)
    } catch {
      setDetail(null)
    }
  }

  if (!Number.isFinite(runId)) {
    return (
      <CecchinoLabShell>
        <p className="p-6 text-[var(--lab-err)]">Run ID non valido</p>
      </CecchinoLabShell>
    )
  }

  const competitionOptions = comps.data?.map((c) => c.competition_name) ?? []

  return (
    <CecchinoLabShell>
      <div className="mx-auto flex max-w-[1400px] flex-col gap-8 px-4 py-6 md:px-6">
        {overview.loading && !overview.data ? <HistoricalRunSkeleton rows={2} /> : null}
        {overview.error ? (
          <HistoricalRunSectionError title="Overview" error={overview.error} onRetry={() => void loadCore()} />
        ) : null}
        {overview.data ? (
          <>
            <HistoricalRunHeader
              overview={overview.data}
              competitions={competitionOptions}
            />
            <HistoricalRunLiveProgress overview={overview.data} />
            <HistoricalRunFilterBar
              filters={filters}
              competitions={competitionOptions}
              eligibleSample={overview.data.active_eligible_sample}
              isProvisional={overview.data.is_provisional}
              onChange={setFilters}
              onReset={() => setFilters({})}
            />
            <HistoricalRunV1Pulse overview={overview.data} />
            <HistoricalRunModuleCoveragePanel coverage={overview.data.module_coverage} />
          </>
        ) : null}

        <Section
          loading={markets.loading}
          error={markets.error}
          title="Mercati"
          onRetry={() => void loadCore()}
        >
          {markets.data ? <HistoricalRunMarketOverview markets={markets.data} /> : null}
        </Section>

        <Section
          loading={ratings.loading}
          error={ratings.error}
          title="Rating"
          onRetry={() => void loadCore()}
        >
          {ratings.data ? (
            <HistoricalRunRatingHeatmap
              bands={ratings.data.bands}
              matrix={ratings.data.matrix}
              warning={ratings.data.warning}
            />
          ) : null}
        </Section>

        <Section loading={purch.loading} error={purch.error} title="Acquistabilità" onRetry={() => void loadCore()}>
          {purch.data ? <HistoricalRunPurchasability data={purch.data} /> : null}
        </Section>

        <Section loading={signals.loading} error={signals.error} title="Segnali" onRetry={() => void loadCore()}>
          {signals.data ? <HistoricalRunSignalModelsFromDashboard data={signals.data} /> : null}
        </Section>

        <Section loading={balance.loading} error={balance.error} title="Balance" onRetry={() => void loadCore()}>
          {balance.data ? <HistoricalRunBalance data={balance.data} /> : null}
        </Section>

        <Section loading={gi.loading} error={gi.error} title="Intensità Goal" onRetry={() => void loadCore()}>
          {gi.data ? <HistoricalRunGoalIntensity data={gi.data} /> : null}
        </Section>

        <Section loading={comps.loading} error={comps.error} title="Campionati" onRetry={() => void loadCore()}>
          {comps.data ? (
            <HistoricalRunCompetitions
              competitions={comps.data}
              onSelect={(c) => setFilters({ ...filters, competition: c })}
            />
          ) : null}
        </Section>

        <Section
          loading={timeline.loading}
          error={timeline.error}
          title="Timeline"
          onRetry={() => void loadLazy()}
        >
          {timeline.data ? (
            <HistoricalRunTimeline
              points={timeline.data.points}
              granularity={granularity}
              onGranularity={(g) => {
                setGranularity(g)
                setTimeline((s) => ({ ...s, loading: true }))
              }}
            />
          ) : null}
        </Section>

        <Section
          loading={patterns.loading}
          error={patterns.error}
          title="Pattern"
          onRetry={() => void loadLazy()}
        >
          {patterns.data ? <HistoricalRunPatterns {...patterns.data} /> : null}
        </Section>

        <Section loading={matches.loading} error={matches.error} title="Match" onRetry={() => void loadCore()}>
          {matches.data ? (
            <HistoricalRunMatches
              items={matches.data.items}
              total={matches.data.total}
              offset={matches.data.offset}
              limit={matches.data.limit}
              onPage={(off) => setMatchOffset(off)}
              onOpen={(id) => void openMatch(id)}
            />
          ) : null}
        </Section>

        <Section
          loading={exclusions.loading}
          error={exclusions.error}
          title="Esclusioni"
          onRetry={() => void loadLazy()}
        >
          {exclusions.data ? (
            <HistoricalRunExclusions
              items={exclusions.data.items}
              total={exclusions.data.total}
            />
          ) : null}
        </Section>
      </div>

      {detail ? (
        <HistoricalRunMatchDetail detail={detail} onClose={() => setDetail(null)} />
      ) : null}
    </CecchinoLabShell>
  )
}

function Section({
  loading,
  error,
  title,
  onRetry,
  children,
}: {
  loading: boolean
  error: string | null
  title: string
  onRetry: () => void
  children: ReactNode
}) {
  if (error) return <HistoricalRunSectionError title={title} error={error} onRetry={onRetry} />
  if (loading && !children) return <HistoricalRunSkeleton rows={2} />
  return <>{children}</>
}
