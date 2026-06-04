import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  CecchinoTodayDetailPanel,
  CecchinoTodayDetailPlaceholder,
} from '../components/cecchino/CecchinoTodayDetailPanel'
import { CecchinoTodayFixtureList, type TodayFlatFixture } from '../components/cecchino/CecchinoTodayFixtureList'
import { CecchinoTodayPageHeader } from '../components/cecchino/CecchinoTodayPageHeader'
import { CecchinoTodayScanSummary } from '../components/cecchino/CecchinoTodayScanSummary'
import { todayPageGrid, todaySectionTitle } from '../components/cecchino/cecchinoTodayStyles'
import {
  getCecchinoTodayDetail,
  getCecchinoTodayList,
  scanCecchinoToday,
  type CecchinoTodayDetailResponse,
  type CecchinoTodayListResponse,
  type CecchinoTodayScanReport,
} from '../lib/cecchinoTodayApi'
import { formatFetchError } from '../utils/formatFetchError'

function todayIsoRome(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome' }).format(new Date())
}

export function CecchinoTodayPage() {
  const [scanDate, setScanDate] = useState(todayIsoRome())
  const [list, setList] = useState<CecchinoTodayListResponse | null>(null)
  const [scanReport, setScanReport] = useState<CecchinoTodayScanReport | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<CecchinoTodayDetailResponse | null>(null)
  const [listLoading, setListLoading] = useState(false)
  const [scanLoading, setScanLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

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
    const load = async () => {
      setListError(null)
      setListLoading(true)
      try {
        const data = await getCecchinoTodayList({ date: scanDate, timezone: 'Europe/Rome' })
        setList(data)
      } catch (e) {
        setListError(formatFetchError(e))
        setList(null)
      } finally {
        setListLoading(false)
      }
    }
    void load()
  }, [scanDate])

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

  const handleScan = async () => {
    setScanError(null)
    setScanLoading(true)
    try {
      const report = await scanCecchinoToday({ scan_date: scanDate, timezone: 'Europe/Rome' })
      setScanReport(report)
      await loadList(scanDate)
    } catch (e) {
      setScanError(formatFetchError(e))
    } finally {
      setScanLoading(false)
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
        scanDate={scanDate}
        onScanDateChange={setScanDate}
        onScan={() => void handleScan()}
        scanLoading={scanLoading}
      />

      {scanError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
          {scanError}
        </p>
      )}

      {scanReport && scanReport.status === 'ok' && (
        <CecchinoTodayScanSummary report={scanReport} />
      )}

      <div className={todayPageGrid}>
        <CecchinoTodayFixtureList
          fixtures={flatFixtures}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={listLoading || scanLoading}
          error={listError}
          scanDate={scanDate}
          onScan={() => void handleScan()}
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
