import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  CecchinoTodayDetailPanel,
  CecchinoTodayDetailPlaceholder,
} from '../components/cecchino/CecchinoTodayDetailPanel'
import { CecchinoTodayDayTabs } from '../components/cecchino/CecchinoTodayDayTabs'
import { CecchinoTodayExcludedPanel } from '../components/cecchino/CecchinoTodayExcludedPanel'
import { CecchinoTodayFixtureList, type TodayFlatFixture } from '../components/cecchino/CecchinoTodayFixtureList'
import { CecchinoTodayPageHeader } from '../components/cecchino/CecchinoTodayPageHeader'
import { CecchinoTodayScanSummary } from '../components/cecchino/CecchinoTodayScanSummary'
import { todayPageGrid, todaySectionTitle } from '../components/cecchino/cecchinoTodayStyles'
import {
  getCecchinoTodayDays,
  getCecchinoTodayDetail,
  getCecchinoTodayList,
  scanCecchinoTodayToday,
  scanCecchinoTodayTomorrow,
  todayIsoRome,
  tomorrowIsoRome,
  type CecchinoTodayDay,
  type CecchinoTodayDetailResponse,
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
  const [scanTodayLoading, setScanTodayLoading] = useState(false)
  const [scanTomorrowLoading, setScanTomorrowLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [excludedOpen, setExcludedOpen] = useState(false)
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
      const today = daysRes?.today ?? todayIsoRome()
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

  const handleScanToday = async () => {
    setScanError(null)
    setScanTodayLoading(true)
    try {
      const report = await scanCecchinoTodayToday()
      setScanReport(report)
      await loadDays()
      const today = todayIsoRome()
      setSelectedDay(today)
      await loadList(today)
    } catch (e) {
      setScanError(formatFetchError(e))
    } finally {
      setScanTodayLoading(false)
    }
  }

  const handleScanTomorrow = async () => {
    setScanError(null)
    setScanTomorrowLoading(true)
    try {
      const report = await scanCecchinoTodayTomorrow()
      setScanReport(report)
      await loadDays()
      const tomorrow = tomorrowIsoRome()
      setSelectedDay(tomorrow)
      await loadList(tomorrow)
    } catch (e) {
      setScanError(formatFetchError(e))
    } finally {
      setScanTomorrowLoading(false)
    }
  }

  const flatFixtures = useMemo((): TodayFlatFixture[] => {
    if (!list) return []
    const out: TodayFlatFixture[] = []
    for (const c of list.countries) {
      for (const l of c.leagues) {
        for (const f of l.fixtures) {
          out.push({ country: c.country_name, league: l.league_name, fixture: f })
        }
      }
    }
    return out
  }, [list])

  return (
    <div className="mx-auto w-full max-w-[1280px] space-y-6">
      <CecchinoTodayPageHeader
        onScanToday={() => void handleScanToday()}
        onScanTomorrow={() => void handleScanTomorrow()}
        scanTodayLoading={scanTodayLoading}
        scanTomorrowLoading={scanTomorrowLoading}
      />

      {scanError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
          {scanError}
        </p>
      )}

      {scanReport && scanReport.status === 'ok' && (
        <CecchinoTodayScanSummary report={scanReport} onShowExcluded={showExcludedPanel} />
      )}

      {!daysLoading && days.length > 0 && (
        <CecchinoTodayDayTabs
          days={days}
          selectedDay={selectedDay}
          onSelectDay={setSelectedDay}
        />
      )}

      <CecchinoTodayExcludedPanel
        selectedDay={selectedDay}
        open={excludedOpen}
        onToggle={() => setExcludedOpen((o) => !o)}
        onRegisterLoad={registerExcludedLoad}
      />

      <div className={todayPageGrid}>
        <CecchinoTodayFixtureList
          fixtures={flatFixtures}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={listLoading}
          error={listError}
          selectedDay={selectedDay}
          scanMeta={list?.scan_meta}
          onScanToday={() => void handleScanToday()}
        />

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
    </div>
  )
}
