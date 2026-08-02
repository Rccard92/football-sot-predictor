import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { CecchinoLabShell } from '../components/cecchino-data-lab/CecchinoLabShell'
import { HistoricalKpiActivationDrawer } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiActivationDrawer'
import { HistoricalKpiActivationsTable } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiActivationsTable'
import { HistoricalKpiEmptyState } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiEmptyState'
import { HistoricalKpiHeatmap } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiHeatmap'
import { HistoricalKpiMetricRibbon } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiMetricRibbon'
import { HistoricalKpiRatingBucketCarousel } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiRatingBucketCarousel'
import { HistoricalKpiSignalsFilters as HistoricalKpiSignalsFiltersBar, HistoricalKpiPurchasabilityImpactCard } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiSignalsFilters'
import { HistoricalKpiSignalsHeader } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiSignalsHeader'
import { HistoricalKpiSkeleton } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiSkeleton'
import { HistoricalKpiTimeline } from '../components/cecchino-data-lab/historical-kpi/HistoricalKpiTimeline'
import { HistoricalRunSectionError } from '../components/cecchino-data-lab/historical-run/HistoricalRunSectionError'
import {
  getHistoricalKpiSignalActivations,
  getHistoricalKpiSignalsSummary,
  getHistoricalKpiSignalsTimeline,
  type HistoricalKpiActivationRow,
  type HistoricalKpiActivationsResponse,
  type HistoricalKpiSignalsFilters,
  type HistoricalKpiSignalsSummary,
  type HistoricalKpiTimelineResponse,
} from '../lib/cecchinoLabApi'

type SectionState<T> = { data: T | null; error: string | null; loading: boolean }

const ACTIVATIONS_LIMIT = 50

const DEFAULT_FILTERS: HistoricalKpiSignalsFilters = {
  quote_type: 'real',
}

function parseFiltersFromSearch(search: string): HistoricalKpiSignalsFilters {
  const params = new URLSearchParams(search)
  const quoteRaw = params.get('quote_type')
  const quote_type: HistoricalKpiSignalsFilters['quote_type'] =
    quoteRaw === 'derived' || quoteRaw === 'all' ? quoteRaw : 'real'

  const purchRaw = params.get('purchasability_min_score')
  let purchasability_min_score: number | undefined
  if (purchRaw != null && purchRaw !== '') {
    const n = Number(purchRaw)
    if (Number.isFinite(n) && n >= 0 && n <= 100) {
      purchasability_min_score = Math.round(n)
    }
  }

  return {
    competition: params.get('competition') || undefined,
    date_from: params.get('date_from') || undefined,
    date_to: params.get('date_to') || undefined,
    rating_bucket: params.get('rating_bucket') || undefined,
    selection_key: params.get('selection_key') || undefined,
    evaluation_status: params.get('evaluation_status') || undefined,
    quote_type,
    purchasability_min_score,
  }
}

function filtersToSearchParams(filters: HistoricalKpiSignalsFilters): URLSearchParams {
  const params = new URLSearchParams()
  const merged = { ...DEFAULT_FILTERS, ...filters }
  for (const [k, v] of Object.entries(merged)) {
    if (v != null && String(v).trim() !== '') params.set(k, String(v))
  }
  return params
}

function idleSection<T>(): SectionState<T> {
  return { data: null, error: null, loading: false }
}

export function CecchinoLabHistoricalKpiSignalsPage() {
  const { runId: runIdParam } = useParams()
  const runId = Number(runIdParam)
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(
    () => parseFiltersFromSearch(searchParams.toString()),
    [searchParams],
  )

  const [summary, setSummary] = useState<SectionState<HistoricalKpiSignalsSummary>>({
    data: null,
    error: null,
    loading: true,
  })
  const [timeline, setTimeline] = useState<SectionState<HistoricalKpiTimelineResponse>>(idleSection())
  const [activations, setActivations] = useState<SectionState<HistoricalKpiActivationsResponse>>(
    idleSection(),
  )
  const [activationsOffset, setActivationsOffset] = useState(0)
  const [drawerRow, setDrawerRow] = useState<HistoricalKpiActivationRow | null>(null)
  const openDrawerAfterLoad = useRef(false)

  const setFilters = useCallback(
    (next: HistoricalKpiSignalsFilters) => {
      setActivationsOffset(0)
      setSearchParams(filtersToSearchParams(next), { replace: true })
    },
    [setSearchParams],
  )

  const loadTimeline = useCallback(
    async (signal: AbortSignal) => {
      setTimeline((s) => ({ ...s, loading: true, error: null }))
      try {
        const data = await getHistoricalKpiSignalsTimeline(runId, filters, 'matchday', { signal })
        if (signal.aborted) return
        setTimeline({ data, error: null, loading: false })
      } catch (e) {
        if (signal.aborted) return
        setTimeline({
          data: null,
          error: e instanceof Error ? e.message : 'Errore timeline',
          loading: false,
        })
      }
    },
    [runId, filters],
  )

  const loadActivations = useCallback(
    async (signal: AbortSignal, offset: number, openFirst: boolean) => {
      setActivations((s) => ({ ...s, loading: true, error: null }))
      try {
        const data = await getHistoricalKpiSignalActivations(
          runId,
          filters,
          { limit: ACTIVATIONS_LIMIT, offset },
          { signal },
        )
        if (signal.aborted) return
        setActivations({ data, error: null, loading: false })
        if (openFirst && data.items.length > 0) {
          setDrawerRow(data.items[0])
        }
      } catch (e) {
        if (signal.aborted) return
        setActivations({
          data: null,
          error: e instanceof Error ? e.message : 'Errore attivazioni',
          loading: false,
        })
      }
    },
    [runId, filters],
  )

  const loadPrimary = useCallback(
    (signal: AbortSignal) => {
      if (!Number.isFinite(runId)) return

      setSummary((s) => ({ ...s, loading: true, error: null }))

      void (async () => {
        try {
          const summaryData = await getHistoricalKpiSignalsSummary(runId, filters, { signal })
          if (signal.aborted) return
          setSummary({ data: summaryData, error: null, loading: false })

          const openFirst = openDrawerAfterLoad.current
          openDrawerAfterLoad.current = false

          await Promise.all([
            loadTimeline(signal),
            loadActivations(signal, 0, openFirst),
          ])
          if (!signal.aborted) setActivationsOffset(0)
        } catch (e) {
          if (signal.aborted) return
          setSummary({
            data: null,
            error: e instanceof Error ? e.message : 'Errore riepilogo KPI',
            loading: false,
          })
        }
      })()
    },
    [runId, filters, loadTimeline, loadActivations],
  )

  useEffect(() => {
    if (!Number.isFinite(runId)) return undefined
    const controller = new AbortController()
    loadPrimary(controller.signal)
    return () => controller.abort()
  }, [runId, filters, loadPrimary])

  const handleRefresh = () => {
    if (!Number.isFinite(runId)) return
    const controller = new AbortController()
    loadPrimary(controller.signal)
  }

  const handleReset = () => {
    setDrawerRow(null)
    openDrawerAfterLoad.current = false
    setActivationsOffset(0)
    setSearchParams(filtersToSearchParams(DEFAULT_FILTERS), { replace: true })
  }

  const handleHeatmapClick = (ratingBucket: string, selectionKey: string) => {
    openDrawerAfterLoad.current = true
    setFilters({
      ...filters,
      rating_bucket: ratingBucket,
      selection_key: selectionKey,
    })
  }

  const handleBucketSelect = (ratingBucket: string) => {
    setFilters({
      ...filters,
      rating_bucket: filters.rating_bucket === ratingBucket ? undefined : ratingBucket,
    })
  }

  const handleActivationsPage = (offset: number) => {
    if (!Number.isFinite(runId)) return
    setActivationsOffset(offset)
    const controller = new AbortController()
    void loadActivations(controller.signal, offset, false)
  }

  if (!Number.isFinite(runId)) {
    return (
      <CecchinoLabShell className="p-6">
        <p className="text-[var(--lab-err)]">Run ID non valido.</p>
        <Link to="/cecchino-lab" className="mt-2 inline-block text-sm text-[var(--lab-cyan)]">
          ← Cecchino Lab
        </Link>
      </CecchinoLabShell>
    )
  }

  const availableFilters = summary.data?.available_filters ?? {
    competitions: [],
    selection_keys: [],
    date_min: null,
    date_max: null,
  }

  return (
    <CecchinoLabShell className="p-4 md:p-6">
      <div className="space-y-6" data-testid="historical-kpi-page">
        {summary.loading && !summary.data ? (
          <HistoricalKpiSkeleton rows={2} />
        ) : summary.error ? (
          <HistoricalRunSectionError
            title="Errore riepilogo KPI"
            error={summary.error}
            onRetry={handleRefresh}
          />
        ) : summary.data ? (
          <HistoricalKpiSignalsHeader run={summary.data.run} />
        ) : null}

        <HistoricalKpiSignalsFiltersBar
          filters={filters}
          availableFilters={availableFilters}
          onChange={setFilters}
          onRefresh={handleRefresh}
          onReset={handleReset}
        />

        {summary.data?.purchasability_filter?.enabled ? (
          <HistoricalKpiPurchasabilityImpactCard
            impact={summary.data.purchasability_filter}
            unsupportedReason={summary.data.reason}
            message={summary.data.message}
          />
        ) : null}

        {summary.loading && summary.data ? <HistoricalKpiSkeleton rows={1} /> : null}

        {summary.data ? (
          <>
            <HistoricalKpiMetricRibbon
              real={summary.data.overall.real}
              synthetic={summary.data.overall.synthetic}
              quoteType={filters.quote_type}
            />

            <HistoricalKpiRatingBucketCarousel
              buckets={summary.data.by_rating_bucket}
              activeRatingBucket={filters.rating_bucket}
              quoteType={filters.quote_type}
              onSelect={handleBucketSelect}
            />

            <HistoricalKpiHeatmap
              heatmap={summary.data.heatmap}
              quoteType={filters.quote_type}
              activeRatingBucket={filters.rating_bucket}
              activeSelectionKey={filters.selection_key}
              onCellClick={handleHeatmapClick}
            />
          </>
        ) : summary.loading ? (
          <HistoricalKpiSkeleton rows={4} />
        ) : !summary.error ? (
          <HistoricalKpiEmptyState message="Nessun dato KPI disponibile per questo run." />
        ) : null}

        {timeline.loading && !timeline.data ? (
          <HistoricalKpiSkeleton rows={3} />
        ) : timeline.error ? (
          <HistoricalRunSectionError
            title="Errore timeline KPI"
            error={timeline.error}
            onRetry={() => {
              const c = new AbortController()
              void loadTimeline(c.signal)
            }}
          />
        ) : timeline.data ? (
          <HistoricalKpiTimeline timeline={timeline.data} quoteType={filters.quote_type} />
        ) : null}

        {activations.loading && !activations.data ? (
          <HistoricalKpiSkeleton rows={4} />
        ) : activations.error ? (
          <HistoricalRunSectionError
            title="Errore attivazioni KPI"
            error={activations.error}
            onRetry={() => handleActivationsPage(activationsOffset)}
          />
        ) : activations.data ? (
          <HistoricalKpiActivationsTable
            items={activations.data.items}
            total={activations.data.total}
            offset={activations.data.offset}
            limit={ACTIVATIONS_LIMIT}
            onRowClick={setDrawerRow}
            onPage={handleActivationsPage}
          />
        ) : null}
      </div>

      <HistoricalKpiActivationDrawer row={drawerRow} onClose={() => setDrawerRow(null)} />
    </CecchinoLabShell>
  )
}
