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
import { CecchinoTodayFixtureList } from '../components/cecchino/CecchinoTodayFixtureList'
import { CecchinoTodayPageHeader } from '../components/cecchino/CecchinoTodayPageHeader'
import { CecchinoTodayScanSummary } from '../components/cecchino/CecchinoTodayScanSummary'
import { CecchinoDayTimeline } from '../components/cecchino/CecchinoDayTimeline'
import { todayPageGrid, todaySectionTitle, todayStickyListColumn } from '../components/cecchino/cecchinoTodayStyles'
import {
  getCecchinoTodayDays,
  getCecchinoTodayDetail,
  getCecchinoTodayList,
  revalidateCecchinoTodayDay,
  scanCecchinoTodayDay,
  todayIsoRome,
  updateCecchinoTodayResults,
  type CecchinoTodayDay,
  type CecchinoTodayDetailResponse,
  type CecchinoTodayListCountry,
  type CecchinoTodayListResponse,
  type CecchinoTodayScanReport,
} from '../lib/cecchinoTodayApi'
import { formatFetchError } from '../utils/formatFetchError'

export function CecchinoTodayPage() {
  const [selectedDay, setSelectedDay] = useState(todayIsoRome())
  const [days, setDays] = useState<CecchinoTodayDay[]>([])
  const [list, setList] = useState<CecchinoTodayListResponse | null>(null)
  const [scanReport, setScanReport] = useState<CecchinoTodayScanReport | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<CecchinoTodayDetailResponse | null>(null)
  const [listLoading, setListLoading] = useState(false)
  const [daysLoading, setDaysLoading] = useState(false)
  const [scanDayLoading, setScanDayLoading] = useState(false)
  const [updateResultsLoading, setUpdateResultsLoading] = useState(false)
  const [revalidateLoading, setRevalidateLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [excludedOpen, setExcludedOpen] = useState(false)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [countryFilter, setCountryFilter] = useState('')
  const [leagueFilter, setLeagueFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const dayNavReady = useRef(false)
  const loadExcludedRef = useRef<(() => Promise<void>) | null>(null)

  const registerExcludedLoad = useCallback((loader: (() => Promise<void>) | null) => {
    loadExcludedRef.current = loader
  }, [])

  const showExcludedPanel = useCallback(() => {
    setExcludedOpen(true)
    void loadExcludedRef.current?.()
  }, [])

  const loadDays = useCallback(async () => {
    setDaysLoading(true)
    try {
      const res = await getCecchinoTodayDays()
      setDays(res.days)
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

  useEffect(() => {
    const init = async () => {
      const daysRes = await loadDays()
      const today = daysRes?.selected_default ?? daysRes?.today ?? todayIsoRome()
      setSelectedDay(today)
      await loadList(today)
      dayNavReady.current = true
    }
    void init()
  }, [loadDays, loadList])

  useEffect(() => {
    if (!dayNavReady.current) return
    setSelectedId(null)
    setDetail(null)
    void loadList(selectedDay)
  }, [selectedDay, loadList])

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

  const handleScanDay = async (forceRescan: boolean) => {
    setActionError(null)
    setScanDayLoading(true)
    try {
      const report = await scanCecchinoTodayDay({ date: selectedDay, forceRescan })
      if (report.status === 'ok') {
        setScanReport(report)
      }
      await loadDays()
      await loadList(selectedDay)
    } catch (e) {
      setActionError(formatFetchError(e))
    } finally {
      setScanDayLoading(false)
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

  return (
    <div className="mx-auto w-full max-w-[1280px] space-y-6">
      <CecchinoTodayPageHeader
        isScanned={isScanned}
        scanDayLoading={scanDayLoading}
        updateResultsLoading={updateResultsLoading}
        revalidateLoading={revalidateLoading}
        onScanDay={(force) => void handleScanDay(force)}
        onUpdateResults={() => void handleUpdateResults()}
        onRevalidateDay={() => void handleRevalidateDay()}
      />

      {actionError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
          {actionError}
        </p>
      )}

      {scanReport && scanReport.status === 'ok' && (
        <CecchinoTodayScanSummary report={scanReport} onShowExcluded={showExcludedPanel} />
      )}

      {!daysLoading && days.length > 0 && (
        <CecchinoDayTimeline days={days} selectedDay={selectedDay} onSelectDay={setSelectedDay} />
      )}

      <CecchinoTodayDaySummary
        selectedDay={selectedDay}
        summary={list?.summary ?? null}
        isScanned={isScanned}
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

      <div className={todayPageGrid}>
        <div className={todayStickyListColumn}>
          <CecchinoTodayFixtureList
            countries={filteredCountries}
            selectedId={selectedId}
            onSelect={setSelectedId}
            loading={listLoading}
            error={listError}
            selectedDay={selectedDay}
            isScanned={isScanned}
            hasActiveFilters={hasActiveFilters}
            totalBeforeFilter={totalBeforeFilter}
            onScanDay={() => void handleScanDay(false)}
          />
        </div>

        <section className="min-w-0 space-y-4">
          <h2 className={todaySectionTitle}>Dettaglio analisi</h2>
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

      <CecchinoTodayExcludedPanel
        selectedDay={selectedDay}
        open={excludedOpen}
        onToggle={() => setExcludedOpen((o) => !o)}
        onRegisterLoad={registerExcludedLoad}
      />
    </div>
  )
}
