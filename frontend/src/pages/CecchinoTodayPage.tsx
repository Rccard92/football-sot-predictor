import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  CecchinoTodayDetailPanel,
  CecchinoTodayDetailPlaceholder,
} from '../components/cecchino/CecchinoTodayDetailPanel'
import { CecchinoTodayDaySummary } from '../components/cecchino/CecchinoTodayDaySummary'
import { CecchinoTodayExcludedPanel } from '../components/cecchino/CecchinoTodayExcludedPanel'
import {
  CecchinoTodayFilters,
  type StatusFilter,
} from '../components/cecchino/CecchinoTodayFilters'
import { CecchinoTodayFixtureDrawer } from '../components/cecchino/CecchinoTodayFixtureDrawer'
import { CecchinoTodayFixtureList } from '../components/cecchino/CecchinoTodayFixtureList'
import { CecchinoTodayPageHeader } from '../components/cecchino/CecchinoTodayPageHeader'
import { CecchinoTodayScanProgressCard } from '../components/cecchino/CecchinoTodayScanProgressCard'
import { CecchinoTodayScanSummary } from '../components/cecchino/CecchinoTodayScanSummary'
import { CecchinoDayTimeline } from '../components/cecchino/CecchinoDayTimeline'
import { todayPageGrid, todaySectionTitle, todayStickyListColumn } from '../components/cecchino/cecchinoTodayStyles'
import {
  getCecchinoTodayDays,
  getCecchinoTodayDetail,
  getCecchinoTodayLatestScanJob,
  getCecchinoTodayList,
  getCecchinoTodayScanJob,
  logCecchinoTodayDebug,
  refreshBetfairOdds,
  recomputeCecchino,
  revalidateCecchinoTodayDay,
  SCAN_JOB_POLL_MS,
  startCecchinoTodayScanDay,
  todayIsoRome,
  updateCecchinoTodayResults,
  type CecchinoKpiV2Panel,
  type CecchinoOddsMeta,
  type CecchinoTodayDay,
  type CecchinoTodayDetailResponse,
  type CecchinoTodayListCountry,
  type CecchinoTodayListResponse,
  type CecchinoTodayScanJob,
  type CecchinoTodayScanReport,
} from '../lib/cecchinoTodayApi'
import { formatFetchError } from '../utils/formatFetchError'
import { AdminHttpError } from '../lib/api'

const POLL_RETRY_MAX = 3

function jobToScanReport(job: CecchinoTodayScanJob): CecchinoTodayScanReport {
  const rs = job.result_summary
  return {
    status: 'ok',
    version: '',
    scan_date: job.scan_date,
    fixtures_found: Number(rs?.fixtures_found ?? job.fixtures_found),
    total_discovered: Number(rs?.fixtures_found ?? job.fixtures_found),
    eligible: job.eligible_count,
    excluded: job.excluded_summary ?? {},
    excluded_total: job.excluded_count,
    fixtures_processed: job.fixtures_checked,
    warnings: job.warnings ?? [],
    errors: job.errors ?? [],
    excluded_summary: job.excluded_summary ?? {},
    result_summary: rs ?? undefined,
  } as CecchinoTodayScanReport & { result_summary?: typeof rs }
}

export function CecchinoTodayPage() {
  const [selectedDay, setSelectedDay] = useState(todayIsoRome())
  const [days, setDays] = useState<CecchinoTodayDay[]>([])
  const [list, setList] = useState<CecchinoTodayListResponse | null>(null)
  const [scanReport, setScanReport] = useState<CecchinoTodayScanReport | null>(null)
  const [activeJob, setActiveJob] = useState<CecchinoTodayScanJob | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [listHidden, setListHidden] = useState(false)
  const [fixtureDrawerOpen, setFixtureDrawerOpen] = useState(false)
  const [detail, setDetail] = useState<CecchinoTodayDetailResponse | null>(null)
  const [listLoading, setListLoading] = useState(false)
  const [daysLoading, setDaysLoading] = useState(false)
  const [scanDayLoading, setScanDayLoading] = useState(false)
  const [updateResultsLoading, setUpdateResultsLoading] = useState(false)
  const [revalidateLoading, setRevalidateLoading] = useState(false)
  const [recomputeLoading, setRecomputeLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [refreshBetfairLoading, setRefreshBetfairLoading] = useState(false)
  const [refreshBetfairMsg, setRefreshBetfairMsg] = useState<{
    text: string
    tone: 'ok' | 'warn' | 'err'
  } | null>(null)

  const handleKpiPanelUpdate = useCallback((panel: CecchinoKpiV2Panel, oddsMeta?: CecchinoOddsMeta) => {
    setDetail((prev) => {
      if (!prev || prev.status !== 'ok') return prev
      const merged: CecchinoKpiV2Panel = {
        ...panel,
        odds_meta: oddsMeta ?? panel.odds_meta,
      }
      return {
        ...prev,
        kpi_panel_v2: merged,
        kpi_panel: merged,
      }
    })
  }, [])

  const handleRefreshBetfairOdds = useCallback(async () => {
    if (selectedId == null) return
    setRefreshBetfairLoading(true)
    setRefreshBetfairMsg(null)
    try {
      const res = await refreshBetfairOdds(selectedId, { force: true, rebuild_kpi: true })
      if (res.status === 'budget_blocked') {
        setRefreshBetfairMsg({
          text: res.message ?? 'Budget API bloccato',
          tone: 'warn',
        })
        return
      }
      if (res.status !== 'ok') {
        setRefreshBetfairMsg({
          text: res.message ?? 'Refresh quote non riuscito',
          tone: 'err',
        })
        return
      }
      if (res.kpi_panel) {
        handleKpiPanelUpdate(res.kpi_panel, res.bookmaker ?? res.kpi_panel.odds_meta)
      }
      setRefreshBetfairMsg({
        text: res.changed ? 'Quote Betfair aggiornate' : 'Nessuna variazione quote',
        tone: res.changed ? 'ok' : 'warn',
      })
    } catch (e) {
      setRefreshBetfairMsg({
        text: e instanceof Error ? e.message : 'Errore refresh quote Betfair',
        tone: 'err',
      })
    } finally {
      setRefreshBetfairLoading(false)
    }
  }, [selectedId, handleKpiPanelUpdate])

  const [excludedOpen, setExcludedOpen] = useState(false)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [countryFilter, setCountryFilter] = useState('')
  const [leagueFilter, setLeagueFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const dayNavReady = useRef(false)
  const initializedRef = useRef(false)
  const selectedDayRef = useRef(selectedDay)
  const loadExcludedRef = useRef<(() => Promise<void>) | null>(null)
  const pollTimerRef = useRef<number | null>(null)
  const pollFailCountRef = useRef(0)
  const pollJobRef = useRef<(jobId: string, date: string) => Promise<void>>(async () => {})
  const activePollRef = useRef<{ jobId: string; date: string } | null>(null)

  useEffect(() => {
    selectedDayRef.current = selectedDay
  }, [selectedDay])

  const registerExcludedLoad = useCallback((loader: (() => Promise<void>) | null) => {
    loadExcludedRef.current = loader
  }, [])

  const showExcludedPanel = useCallback(() => {
    setExcludedOpen(true)
    void loadExcludedRef.current?.()
  }, [])

  const loadDays = useCallback(async () => {
    logCecchinoTodayDebug('loadDays start', { selectedDay: selectedDayRef.current })
    setDaysLoading(true)
    try {
      const res = await getCecchinoTodayDays()
      setDays(res.days)
      logCecchinoTodayDebug('loadDays done', { selectedDay: selectedDayRef.current })
      return res
    } catch {
      setDays([])
      return null
    } finally {
      setDaysLoading(false)
    }
  }, [])

  const loadList = useCallback(async (date: string) => {
    setListError(null)
    setListLoading(true)
    try {
      const data = await getCecchinoTodayList({ date, timezone: 'Europe/Rome' })
      setList(data)
      if (data.summary.upcoming_count > 0) {
        setStatusFilter('upcoming')
      } else {
        setStatusFilter('all')
      }
      setCountryFilter('')
      setLeagueFilter('')
      setSearchQuery('')
    } catch (e) {
      setListError(formatFetchError(e))
      setList(null)
    } finally {
      setListLoading(false)
    }
  }, [])

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current != null) {
      window.clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
    activePollRef.current = null
  }, [])

  const pollJob = useCallback(
    async (jobId: string, date: string) => {
      try {
        const job = await getCecchinoTodayScanJob(jobId)
        pollFailCountRef.current = 0
        setActiveJob(job)
        logCecchinoTodayDebug('poll tick', { jobId, status: job.status, date })

        if (job.status === 'completed') {
          stopPolling()
          setScanDayLoading(false)
          setScanReport(jobToScanReport(job))
          await loadDays()
          await loadList(date)
          return
        }

        if (job.status === 'failed' || job.status === 'cancelled') {
          stopPolling()
          setScanDayLoading(false)
          setActionError(job.errors?.[0] ?? 'Scansione interrotta')
          await loadDays()
          return
        }

        pollTimerRef.current = window.setTimeout(() => {
          void pollJobRef.current(jobId, date)
        }, SCAN_JOB_POLL_MS)
      } catch (e) {
        pollFailCountRef.current += 1
        if (pollFailCountRef.current >= POLL_RETRY_MAX) {
          stopPolling()
          setScanDayLoading(false)
          setActionError(formatFetchError(e))
          return
        }
        pollTimerRef.current = window.setTimeout(() => {
          void pollJobRef.current(jobId, date)
        }, SCAN_JOB_POLL_MS)
      }
    },
    [loadDays, loadList, stopPolling],
  )

  useEffect(() => {
    pollJobRef.current = pollJob
  }, [pollJob])

  const attachToJob = useCallback(
    (jobId: string, date: string) => {
      const current = activePollRef.current
      if (current?.jobId === jobId && current.date === date) {
        logCecchinoTodayDebug('attachToJob skip — già in poll', { jobId, date })
        return
      }
      stopPolling()
      activePollRef.current = { jobId, date }
      pollFailCountRef.current = 0
      setScanDayLoading(true)
      logCecchinoTodayDebug('attachToJob start poll', { jobId, date })
      void pollJob(jobId, date)
    },
    [pollJob, stopPolling],
  )

  const resumeActiveJobForDay = useCallback(
    async (date: string) => {
      try {
        const latest = await getCecchinoTodayLatestScanJob(date)
        if (!latest) {
          setActiveJob((prev) => (prev?.scan_date === date ? null : prev))
          return
        }

        if (
          (latest.status === 'queued' || latest.status === 'running') &&
          latest.job_id
        ) {
          setActiveJob(latest)
          attachToJob(latest.job_id, date)
          return
        }

        if (latest.scan_date === date) {
          setActiveJob((prev) => {
            if (prev?.scan_date === date && (prev.status === 'queued' || prev.status === 'running')) {
              return prev
            }
            if (latest.status === 'failed' || latest.status === 'completed') {
              return latest
            }
            return prev?.scan_date === date ? null : prev
          })
        }
      } catch {
        /* ignore resume errors */
      }
    },
    [attachToJob],
  )

  useEffect(() => {
    if (initializedRef.current) return
    let cancelled = false

    const init = async () => {
      const daysRes = await loadDays()
      if (cancelled) return
      const today = daysRes?.selected_default ?? daysRes?.today ?? todayIsoRome()
      setSelectedDay(today)
      await loadList(today)
      if (cancelled) return
      try {
        const latest = await getCecchinoTodayLatestScanJob(today)
        if (
          latest &&
          (latest.status === 'queued' || latest.status === 'running') &&
          latest.job_id
        ) {
          setActiveJob(latest)
          attachToJob(latest.job_id, today)
        }
      } catch {
        /* ignore */
      }
      initializedRef.current = true
      dayNavReady.current = true
    }

    void init()
    return () => {
      cancelled = true
      stopPolling()
    }
  }, [attachToJob, loadDays, loadList, stopPolling])

  useEffect(() => {
    if (!dayNavReady.current) return
    const prevPoll = activePollRef.current
    if (prevPoll && prevPoll.date !== selectedDay) {
      stopPolling()
      setScanDayLoading(false)
    }
    setSelectedId(null)
    setListHidden(false)
    setFixtureDrawerOpen(false)
    setDetail(null)
    void loadList(selectedDay)
    void resumeActiveJobForDay(selectedDay)
  }, [selectedDay, loadList, resumeActiveJobForDay, stopPolling])

  useEffect(() => {
    const load = async () => {
      setDetailError(null)
      setDetail(null)
      if (selectedId == null) return
      setDetailLoading(true)
      try {
        const data = await getCecchinoTodayDetail(selectedId)
        setDetail(data)
      } catch (e) {
        setDetailError(formatFetchError(e))
        setDetail(null)
      } finally {
        setDetailLoading(false)
      }
    }
    void load()
  }, [selectedId])

  const handleSelectFixture = useCallback((id: number) => {
    setRefreshBetfairMsg(null)
    setSelectedId(id)
    setFixtureDrawerOpen(false)
  }, [])

  const handleScanDay = async (forceRescan: boolean) => {
    setActionError(null)
    setScanReport(null)
    setScanDayLoading(true)
    logCecchinoTodayDebug('handleScanDay', { date: selectedDay, forceRescan })
    try {
      const start = await startCecchinoTodayScanDay({ date: selectedDay, forceRescan })
      logCecchinoTodayDebug('handleScanDay response', start)

      if (start.status === 'already_scanned') {
        setScanDayLoading(false)
        await loadDays()
        await loadList(selectedDay)
        return
      }

      if (start.status === 'conflict') {
        setScanDayLoading(false)
        setActionError(start.message ?? 'Scansione già in corso')
        if (start.job_id) {
          attachToJob(start.job_id, selectedDay)
        }
        return
      }

      if (start.status === 'queued' || start.status === 'running') {
        if (start.job_id) {
          setActiveJob({
            job_id: start.job_id,
            scan_date: start.scan_date,
            timezone: 'Europe/Rome',
            force_rescan: forceRescan,
            status: start.status,
            current_step: 'fetching_fixtures',
            progress_current: 0,
            progress_total: null,
            progress_pct: null,
            fixtures_found: 0,
            fixtures_checked: 0,
            odds_checked: 0,
            eligible_count: 0,
            excluded_count: 0,
            excluded_summary: {},
            result_summary: null,
            warnings: [],
            errors: [],
            started_at: null,
            finished_at: null,
          })
          attachToJob(start.job_id, selectedDay)
          return
        }
      }

      if (!start.job_id) {
        setScanDayLoading(false)
        setActionError(start.message ?? 'Impossibile avviare la scansione')
        return
      }

      setActiveJob({
        job_id: start.job_id,
        scan_date: start.scan_date,
        timezone: 'Europe/Rome',
        force_rescan: forceRescan,
        status: start.status,
        current_step: 'fetching_fixtures',
        progress_current: 0,
        progress_total: null,
        progress_pct: null,
        fixtures_found: 0,
        fixtures_checked: 0,
        odds_checked: 0,
        eligible_count: 0,
        excluded_count: 0,
        excluded_summary: {},
        result_summary: null,
        warnings: [],
        errors: [],
        started_at: null,
        finished_at: null,
      })
      attachToJob(start.job_id, selectedDay)
    } catch (e) {
      setScanDayLoading(false)
      if (e instanceof AdminHttpError && e.status === 409) {
        setActionError('Scansione già in corso per questa giornata')
      } else if (e instanceof AdminHttpError && e.status === 500) {
        const msg = e.message.toLowerCase()
        if (msg.includes('errore database interno') || msg.includes('database')) {
          setActionError('Errore durante la scansione. Controlla i log backend.')
        } else {
          setActionError(formatFetchError(e))
        }
      } else {
        setActionError(formatFetchError(e))
      }
    }
  }

  const handleUpdateResults = async () => {
    setActionError(null)
    setUpdateResultsLoading(true)
    try {
      await updateCecchinoTodayResults({ date: selectedDay })
      await loadDays()
      await loadList(selectedDay)
    } catch (e) {
      setActionError(formatFetchError(e))
    } finally {
      setUpdateResultsLoading(false)
    }
  }

  const handleRevalidateDay = async () => {
    setActionError(null)
    setRevalidateLoading(true)
    try {
      await revalidateCecchinoTodayDay({ date: selectedDay })
      await loadDays()
      await loadList(selectedDay)
      if (excludedOpen) {
        await loadExcludedRef.current?.()
      }
    } catch (e) {
      setActionError(formatFetchError(e))
    } finally {
      setRevalidateLoading(false)
    }
  }

  const RECOMPUTE_WARNING =
    'Il ricalcolo usa i nuovi pesi Cecchino e aggiorna KPI, segnali e monitoraggio usando i dati già presenti. Non consuma API se refresh quote è disattivato.'

  const handleRecomputeCecchino = async () => {
    if (!window.confirm(RECOMPUTE_WARNING)) return
    setActionError(null)
    setRecomputeLoading(true)
    try {
      const res = await recomputeCecchino({
        date_from: selectedDay,
        date_to: selectedDay,
      })
      setRefreshBetfairMsg({
        tone: 'ok',
        text: `Ricalcolo completato: ${res.fixtures_recomputed}/${res.fixtures_found} partite, ${res.signals_synced} segnali sincronizzati, ${res.signals_evaluated} rivalutati.`,
      })
      await loadDays()
      await loadList(selectedDay)
      if (selectedId != null) {
        const data = await getCecchinoTodayDetail(selectedId)
        setDetail(data)
      }
      if (excludedOpen) {
        await loadExcludedRef.current?.()
      }
    } catch (e) {
      setActionError(formatFetchError(e))
    } finally {
      setRecomputeLoading(false)
    }
  }

  const filteredCountries = useMemo((): CecchinoTodayListCountry[] => {
    if (!list) return []
    const q = searchQuery.trim().toLowerCase()
    const out: CecchinoTodayListCountry[] = []

    for (const country of list.countries) {
      if (countryFilter && country.country_name !== countryFilter) continue

      const leagues = []
      for (const league of country.leagues) {
        if (leagueFilter && league.league_name !== leagueFilter) continue

        const fixtures = league.fixtures.filter((f) => {
          if (statusFilter !== 'all' && f.status !== statusFilter) return false
          if (!q) return true
          const hay = [
            f.home_team_name,
            f.away_team_name,
            league.league_name,
            country.country_name,
          ]
            .filter(Boolean)
            .join(' ')
            .toLowerCase()
          return hay.includes(q)
        })

        if (fixtures.length > 0) {
          leagues.push({ ...league, fixtures })
        }
      }

      if (leagues.length > 0) {
        out.push({ ...country, leagues })
      }
    }
    return out
  }, [list, statusFilter, countryFilter, leagueFilter, searchQuery])

  const availableLeagues = useMemo(() => {
    if (!list) return []
    const names: string[] = []
    for (const c of list.countries) {
      if (countryFilter && c.country_name !== countryFilter) continue
      for (const l of c.leagues) {
        names.push(l.league_name)
      }
    }
    return [...new Set(names)].sort()
  }, [list, countryFilter])

  const totalBeforeFilter = list?.summary.eligible_count ?? 0
  const isScanned = list?.is_scanned ?? false
  const hasActiveFilters =
    statusFilter !== 'all' || !!countryFilter || !!leagueFilter || !!searchQuery.trim()
  const visibleFixtureCount = useMemo(
    () =>
      filteredCountries.reduce(
        (n, c) => n + c.leagues.reduce((ln, l) => ln + l.fixtures.length, 0),
        0,
      ),
    [filteredCountries],
  )

  const listProps = {
    countries: filteredCountries,
    selectedId,
    onSelect: handleSelectFixture,
    loading: listLoading,
    error: listError,
    selectedDay,
    isScanned,
    hasActiveFilters,
    totalBeforeFilter,
    onScanDay: () => void handleScanDay(false),
  }
  const scanInProgress =
    scanDayLoading ||
    (activeJob?.scan_date === selectedDay &&
      (activeJob.status === 'queued' || activeJob.status === 'running'))
  const showProgress =
    activeJob &&
    activeJob.scan_date === selectedDay &&
    (activeJob.status === 'queued' ||
      activeJob.status === 'running' ||
      activeJob.status === 'failed' ||
      activeJob.status === 'completed')

  return (
    <div className="w-full space-y-6">
      <CecchinoTodayPageHeader
        isScanned={isScanned}
        scanDayLoading={scanDayLoading}
        scanInProgress={scanInProgress}
        updateResultsLoading={updateResultsLoading}
        revalidateLoading={revalidateLoading}
        recomputeLoading={recomputeLoading}
        selectedFixtureId={selectedId}
        refreshBetfairLoading={refreshBetfairLoading}
        onScanDay={(force) => void handleScanDay(force)}
        onUpdateResults={() => void handleUpdateResults()}
        onRevalidateDay={() => void handleRevalidateDay()}
        onRecomputeCecchino={isScanned ? () => void handleRecomputeCecchino() : undefined}
        onRefreshBetfairOdds={() => void handleRefreshBetfairOdds()}
      />

      {refreshBetfairMsg && (
        <p
          className={`rounded-lg border px-4 py-2 text-sm ${
            refreshBetfairMsg.tone === 'err'
              ? 'border-red-200 bg-red-50 text-red-800'
              : refreshBetfairMsg.tone === 'warn'
                ? 'border-amber-200 bg-amber-50 text-amber-900'
                : 'border-emerald-200 bg-emerald-50 text-emerald-900'
          }`}
        >
          {refreshBetfairMsg.text}
        </p>
      )}

      {actionError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
          {actionError}
        </p>
      )}

      {showProgress && activeJob ? <CecchinoTodayScanProgressCard job={activeJob} /> : null}

      {scanReport && scanReport.status === 'ok' && !scanInProgress && activeJob?.status !== 'running' ? (
        <CecchinoTodayScanSummary report={scanReport} onShowExcluded={showExcludedPanel} />
      ) : null}

      {!daysLoading && days.length > 0 && (
        <CecchinoDayTimeline days={days} selectedDay={selectedDay} onSelectDay={setSelectedDay} />
      )}

      <CecchinoTodayDaySummary
        selectedDay={selectedDay}
        summary={list?.summary ?? null}
        isScanned={isScanned}
        activeJob={activeJob?.scan_date === selectedDay ? activeJob : null}
      />

      {isScanned && list && (
        <CecchinoTodayFilters
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          countryFilter={countryFilter}
          onCountryFilterChange={setCountryFilter}
          leagueFilter={leagueFilter}
          onLeagueFilterChange={setLeagueFilter}
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          countries={list.filters.countries}
          leagues={availableLeagues}
        />
      )}

      <div className={listHidden ? 'grid grid-cols-1' : todayPageGrid}>
        {/* Lista inline solo da 2xl e se non nascosta */}
        {!listHidden ? (
          <div className={`hidden 2xl:block ${todayStickyListColumn}`}>
            <CecchinoTodayFixtureList {...listProps} />
          </div>
        ) : null}

        <section className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className={todaySectionTitle}>Dettaglio analisi</h2>
            <div className="flex flex-wrap items-center gap-2">
              {/* Sotto 2xl: apre drawer */}
              <button
                type="button"
                onClick={() => setFixtureDrawerOpen(true)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 2xl:hidden"
              >
                Partite eleggibili · {visibleFixtureCount}
              </button>
              {/* Da 2xl: nascondi/mostra lista inline */}
              <button
                type="button"
                onClick={() => setListHidden((v) => !v)}
                className="hidden rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 2xl:inline-flex"
              >
                {listHidden ? 'Mostra partite' : 'Nascondi partite'}
              </button>
            </div>
          </div>
          {detailError && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
              {detailError}
            </p>
          )}
          {selectedId == null && !detailLoading && <CecchinoTodayDetailPlaceholder />}
          {(selectedId != null || detailLoading) && (
            <CecchinoTodayDetailPanel
              detail={detail ?? { status: 'error', message: 'Caricamento…' }}
              loading={detailLoading}
            />
          )}
        </section>
      </div>

      <CecchinoTodayFixtureDrawer
        open={fixtureDrawerOpen}
        onClose={() => setFixtureDrawerOpen(false)}
        title={`Partite eleggibili · ${visibleFixtureCount}`}
      >
        <CecchinoTodayFixtureList {...listProps} />
      </CecchinoTodayFixtureDrawer>

      <CecchinoTodayExcludedPanel
        selectedDay={selectedDay}
        open={excludedOpen}
        onToggle={() => setExcludedOpen((o) => !o)}
        onRegisterLoad={registerExcludedLoad}
      />
    </div>
  )
}
