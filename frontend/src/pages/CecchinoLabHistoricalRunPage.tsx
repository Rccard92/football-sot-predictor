import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
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
  type HistoricalRunOfficialPurchasability,
  type HistoricalRunRatingCell,
  type HistoricalRunSignalsDashboard,
  type HistoricalRunTimelinePoint,
} from '../lib/cecchinoLabApi'

type SectionState<T> = { data: T | null; error: string | null; loading: boolean }

type ModuleId =
  | 'purchasability'
  | 'markets'
  | 'ratings'
  | 'signals'
  | 'balance'
  | 'goal_intensity'
  | 'competitions'
  | 'matches'
  | 'timeline'
  | 'patterns'
  | 'exclusions'

function idleSection<T>(): SectionState<T> {
  return { data: null, error: null, loading: false }
}

export function CecchinoLabHistoricalRunPage() {
  const { runId: runIdParam } = useParams()
  const runId = Number(runIdParam)
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(
    () => parseHistoricalRunFiltersFromSearch(searchParams.toString()),
    [searchParams],
  )

  const [overview, setOverview] = useState<SectionState<HistoricalRunDashboardOverview>>({
    data: null,
    error: null,
    loading: true,
  })
  const [markets, setMarkets] = useState<SectionState<HistoricalRunDashboardMarket[]>>(idleSection())
  const [ratings, setRatings] = useState<
    SectionState<{ bands: string[]; matrix: HistoricalRunRatingCell[]; warning?: string }>
  >(idleSection())
  const [purch, setPurch] = useState<SectionState<HistoricalRunOfficialPurchasability>>(idleSection())
  const [signals, setSignals] = useState<SectionState<HistoricalRunSignalsDashboard>>(idleSection())
  const [balance, setBalance] = useState<SectionState<HistoricalRunBalanceAnalytics>>(idleSection())
  const [gi, setGi] = useState<SectionState<HistoricalRunGoalIntensityAnalytics>>(idleSection())
  const [comps, setComps] = useState<SectionState<HistoricalRunCompetitionAnalytics[]>>(idleSection())
  const [timeline, setTimeline] = useState<
    SectionState<{ points: HistoricalRunTimelinePoint[]; granularity: string }>
  >(idleSection())
  const [patterns, setPatterns] = useState<
    SectionState<{
      positive: HistoricalRunPattern[]
      negative: HistoricalRunPattern[]
      watchlist: HistoricalRunPattern[]
      unstable: HistoricalRunPattern[]
      diagnostics?: HistoricalRunPattern[]
    }>
  >(idleSection())
  const [exclusions, setExclusions] = useState<
    SectionState<{ items: HistoricalRunExclusion[]; total: number }>
  >(idleSection())
  const [matches, setMatches] = useState<
    SectionState<{ items: HistoricalRunMatchRow[]; total: number; offset: number; limit: number }>
  >(idleSection())
  const [matchOffset, setMatchOffset] = useState(0)
  const [granularity, setGranularity] = useState('week')
  const [detail, setDetail] = useState<MatchDetail | null>(null)
  const [openModules, setOpenModules] = useState<Set<ModuleId>>(new Set())

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

  const loadOverview = useCallback(async () => {
    if (!Number.isFinite(runId)) return
    setOverview((s) => ({ ...s, loading: true, error: null }))
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
  }, [runId, filters])

  useEffect(() => {
    void loadOverview()
  }, [loadOverview])

  useEffect(() => {
    const status = overview.data?.run.status
    if (!status || !isHistoricalScanActive(status)) return
    const id = window.setInterval(() => {
      void loadOverview()
    }, 4000)
    return () => window.clearInterval(id)
  }, [overview.data?.run.status, loadOverview])

  const loadModule = useCallback(
    async (id: ModuleId) => {
      if (!Number.isFinite(runId)) return
      const load = async <T,>(fn: () => Promise<T>, setter: (s: SectionState<T>) => void) => {
        setter({ data: null, error: null, loading: true })
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

      switch (id) {
        case 'markets':
          await load(
            async () => (await getHistoricalRunDashboardMarkets(runId, filters)).markets,
            setMarkets,
          )
          break
        case 'ratings':
          await load(async () => {
            const r = await getHistoricalRunDashboardRatings(runId, filters)
            return { bands: r.bands, matrix: r.matrix, warning: r.warning }
          }, setRatings)
          break
        case 'purchasability':
          await load(() => getHistoricalRunDashboardPurchasability(runId, filters), setPurch)
          break
        case 'signals':
          await load(() => getHistoricalRunDashboardSignals(runId, filters), setSignals)
          break
        case 'balance':
          await load(() => getHistoricalRunDashboardBalance(runId, filters), setBalance)
          break
        case 'goal_intensity':
          await load(() => getHistoricalRunDashboardGoalIntensity(runId, filters), setGi)
          break
        case 'competitions':
          await load(
            async () => (await getHistoricalRunDashboardCompetitions(runId, filters)).competitions,
            setComps,
          )
          break
        case 'matches':
          await load(async () => {
            const m = await listHistoricalRunMatches(runId, filters, {
              limit: 50,
              offset: matchOffset,
            })
            return { items: m.items, total: m.total, offset: m.offset, limit: m.limit }
          }, setMatches)
          break
        case 'timeline':
          await load(async () => {
            const t = await getHistoricalRunDashboardTimeline(runId, filters, { granularity })
            return { points: t.points, granularity: t.granularity }
          }, setTimeline)
          break
        case 'patterns':
          await load(async () => {
            const p = await getHistoricalRunDashboardPatterns(runId, filters)
            return {
              positive: p.positive,
              negative: p.negative,
              watchlist: p.watchlist,
              unstable: p.unstable,
              diagnostics: p.diagnostics ?? [],
            }
          }, setPatterns)
          break
        case 'exclusions':
          await load(async () => {
            const ex = await getHistoricalRunDashboardExclusions(runId, filters)
            return { items: ex.items, total: ex.total_excluded }
          }, setExclusions)
          break
      }
    },
    [runId, filters, matchOffset, granularity],
  )

  const toggleModule = useCallback(
    (id: ModuleId) => {
      setOpenModules((prev) => {
        const next = new Set(prev)
        if (next.has(id)) {
          next.delete(id)
          return next
        }
        next.add(id)
        void loadModule(id)
        return next
      })
    },
    [loadModule],
  )

  useEffect(() => {
    if (openModules.has('matches')) void loadModule('matches')
  }, [matchOffset]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (openModules.has('timeline')) void loadModule('timeline')
  }, [granularity]) // eslint-disable-line react-hooks/exhaustive-deps

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
          <HistoricalRunSectionError
            title="Overview"
            error={overview.error}
            onRetry={() => void loadOverview()}
          />
        ) : null}
        {overview.data ? (
          <>
            <HistoricalRunHeader overview={overview.data} competitions={competitionOptions} />
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

            <section>
              <h3 className="mb-2 text-lg font-semibold">Analisi disponibili</h3>
              <p className="mb-4 text-sm text-[var(--lab-muted)]">
                Hub resource-safe: al mount viene caricata solo l&apos;overview. Ogni modulo si
                apre su richiesta.
              </p>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                <Link
                  to={`/cecchino-lab/historical-scans/${runId}/kpi-signals`}
                  className="rounded-xl border p-4 transition hover:border-[var(--lab-cyan)]"
                  style={{ borderColor: 'var(--lab-cyan)', background: 'var(--lab-surface)' }}
                  data-testid="hub-kpi-card"
                >
                  <div className="text-base font-semibold text-[var(--lab-cyan)]">
                    Analisi KPI storico
                  </div>
                  <p className="mt-2 text-sm text-[var(--lab-muted)]">
                    Backtest del Pannello KPI per fasce Rating, pronostico e periodo
                  </p>
                  <span className="mt-3 inline-block text-sm font-medium text-[var(--lab-cyan)]">
                    Apri analisi KPI →
                  </span>
                  <div className="mt-2 text-[11px] text-[var(--lab-muted)]">
                    Resource-safe · nessun dato finché non apri la pagina
                  </div>
                </Link>

                <HubModuleCard
                  title="Acquistabilità V3"
                  description="Score ufficiale V3 e performance per mercato"
                  open={openModules.has('purchasability')}
                  onToggle={() => toggleModule('purchasability')}
                />
                <HubModuleCard
                  title="Mercati"
                  description="Overview mercati storici Bet365"
                  open={openModules.has('markets')}
                  onToggle={() => toggleModule('markets')}
                />
                <HubModuleCard
                  title="Segnali A–F"
                  description="Modelli segnale storici"
                  open={openModules.has('signals')}
                  onToggle={() => toggleModule('signals')}
                />
                <HubModuleCard
                  title="Balance"
                  description="Classi strutturali Balance"
                  open={openModules.has('balance')}
                  onToggle={() => toggleModule('balance')}
                />
                <HubModuleCard
                  title="Intensità Goal"
                  description="Compatibilità intensità goal"
                  open={openModules.has('goal_intensity')}
                  onToggle={() => toggleModule('goal_intensity')}
                />
                <HubModuleCard
                  title="Campionati"
                  description="Breakdown per competizione"
                  open={openModules.has('competitions')}
                  onToggle={() => toggleModule('competitions')}
                />
                <HubModuleCard
                  title="Partite"
                  description="Lista paginata snapshot"
                  open={openModules.has('matches')}
                  onToggle={() => toggleModule('matches')}
                />
                <HubModuleCard
                  title="Timeline"
                  description="Andamento temporale aggregato"
                  open={openModules.has('timeline')}
                  onToggle={() => toggleModule('timeline')}
                />
                <HubModuleCard
                  title="Esclusioni"
                  description="Snapshot non eligible_core"
                  open={openModules.has('exclusions')}
                  onToggle={() => toggleModule('exclusions')}
                />
                <HubModuleCard
                  title="Rating heatmap"
                  description="Matrice rating × mercato (dashboard)"
                  open={openModules.has('ratings')}
                  onToggle={() => toggleModule('ratings')}
                />
                <HubModuleCard
                  title="Pattern"
                  description="Pattern positivi/negativi"
                  open={openModules.has('patterns')}
                  onToggle={() => toggleModule('patterns')}
                />
              </div>
            </section>
          </>
        ) : null}

        {openModules.has('markets') ? (
          <AccordionSection
            title="Mercati"
            loading={markets.loading}
            error={markets.error}
            onRetry={() => void loadModule('markets')}
          >
            {markets.data ? <HistoricalRunMarketOverview markets={markets.data} /> : null}
          </AccordionSection>
        ) : null}

        {openModules.has('ratings') ? (
          <AccordionSection
            title="Rating"
            loading={ratings.loading}
            error={ratings.error}
            onRetry={() => void loadModule('ratings')}
          >
            {ratings.data ? (
              <HistoricalRunRatingHeatmap
                bands={ratings.data.bands}
                matrix={ratings.data.matrix}
                warning={ratings.data.warning}
              />
            ) : null}
          </AccordionSection>
        ) : null}

        {openModules.has('purchasability') ? (
          <AccordionSection
            title="Acquistabilità V3"
            loading={purch.loading}
            error={purch.error}
            onRetry={() => void loadModule('purchasability')}
          >
            {purch.data ? <HistoricalRunPurchasability data={purch.data} runId={runId} /> : null}
          </AccordionSection>
        ) : null}

        {openModules.has('signals') ? (
          <AccordionSection
            title="Segnali"
            loading={signals.loading}
            error={signals.error}
            onRetry={() => void loadModule('signals')}
          >
            {signals.data ? <HistoricalRunSignalModelsFromDashboard data={signals.data} /> : null}
          </AccordionSection>
        ) : null}

        {openModules.has('balance') ? (
          <AccordionSection
            title="Balance"
            loading={balance.loading}
            error={balance.error}
            onRetry={() => void loadModule('balance')}
          >
            {balance.data ? <HistoricalRunBalance data={balance.data} /> : null}
          </AccordionSection>
        ) : null}

        {openModules.has('goal_intensity') ? (
          <AccordionSection
            title="Intensità Goal"
            loading={gi.loading}
            error={gi.error}
            onRetry={() => void loadModule('goal_intensity')}
          >
            {gi.data ? <HistoricalRunGoalIntensity data={gi.data} /> : null}
          </AccordionSection>
        ) : null}

        {openModules.has('competitions') ? (
          <AccordionSection
            title="Campionati"
            loading={comps.loading}
            error={comps.error}
            onRetry={() => void loadModule('competitions')}
          >
            {comps.data ? (
              <HistoricalRunCompetitions
                competitions={comps.data}
                onSelect={(c) => setFilters({ ...filters, competition: c })}
              />
            ) : null}
          </AccordionSection>
        ) : null}

        {openModules.has('timeline') ? (
          <AccordionSection
            title="Timeline"
            loading={timeline.loading}
            error={timeline.error}
            onRetry={() => void loadModule('timeline')}
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
          </AccordionSection>
        ) : null}

        {openModules.has('patterns') ? (
          <AccordionSection
            title="Pattern"
            loading={patterns.loading}
            error={patterns.error}
            onRetry={() => void loadModule('patterns')}
          >
            {patterns.data ? <HistoricalRunPatterns {...patterns.data} /> : null}
          </AccordionSection>
        ) : null}

        {openModules.has('matches') ? (
          <AccordionSection
            title="Match"
            loading={matches.loading}
            error={matches.error}
            onRetry={() => void loadModule('matches')}
          >
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
          </AccordionSection>
        ) : null}

        {openModules.has('exclusions') ? (
          <AccordionSection
            title="Esclusioni"
            loading={exclusions.loading}
            error={exclusions.error}
            onRetry={() => void loadModule('exclusions')}
          >
            {exclusions.data ? (
              <HistoricalRunExclusions
                items={exclusions.data.items}
                total={exclusions.data.total}
              />
            ) : null}
          </AccordionSection>
        ) : null}
      </div>

      {detail ? (
        <HistoricalRunMatchDetail detail={detail} onClose={() => setDetail(null)} />
      ) : null}
    </CecchinoLabShell>
  )
}

function HubModuleCard({
  title,
  description,
  open,
  onToggle,
}: {
  title: string
  description: string
  open: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="rounded-xl border p-4 text-left transition hover:border-[var(--lab-cyan)]"
      style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="text-base font-semibold">{title}</div>
        <span className="text-xs text-[var(--lab-muted)]">{open ? 'Aperto' : 'Carica'}</span>
      </div>
      <p className="mt-2 text-sm text-[var(--lab-muted)]">{description}</p>
    </button>
  )
}

function AccordionSection({
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
  return (
    <section>
      <h3 className="mb-3 text-lg font-semibold">{title}</h3>
      {children}
    </section>
  )
}
