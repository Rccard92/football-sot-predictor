import { useCallback, useEffect, useMemo, useState } from 'react'
import { CecchinoTodayDetailPanel } from '../components/cecchino/CecchinoTodayDetailPanel'
import {
  formatKickoffTime,
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

  const flatFixtures = useMemo(() => {
    if (!list) return []
    const out: Array<{ country: string; league: string; fixture: (typeof list.countries)[0]['leagues'][0]['fixtures'][0] }> = []
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
    <div className="mx-auto max-w-6xl space-y-6 p-4">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold text-white">Cecchino Today</h1>
        <p className="text-sm text-slate-300">
          Discovery manuale partite odierne — solo eleggibili (quote complete, statistiche OK, no leakage).
        </p>
      </header>

      <section className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-600 bg-slate-900/50 p-4">
        <label className="flex flex-col gap-1 text-sm text-slate-300">
          Data scan
          <input
            type="date"
            value={scanDate}
            onChange={(e) => setScanDate(e.target.value)}
            className="rounded border border-slate-500 bg-slate-800 px-2 py-1 text-white"
          />
        </label>
        <button
          type="button"
          onClick={() => void handleScan()}
          disabled={scanLoading}
          className="rounded bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {scanLoading ? 'Scansione…' : 'Aggiorna partite odierne'}
        </button>
      </section>

      {scanError && <p className="text-sm text-red-300">{scanError}</p>}

      {scanReport && (
        <section className="rounded-lg border border-emerald-600/40 bg-emerald-950/20 p-4 text-sm text-emerald-100">
          <p>
            Scan completato — scoperte: {scanReport.total_discovered}, eleggibili: {scanReport.eligible},
            escluse: {scanReport.excluded_total ?? Object.values(scanReport.excluded).reduce((a, b) => a + b, 0)}
          </p>
          {(scanReport.warnings?.length ?? 0) > 0 && (
            <ul className="mt-2 list-inside list-disc text-xs text-amber-200">
              {scanReport.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-white">Partite eleggibili</h2>
          {listLoading && <p className="text-sm text-slate-400">Caricamento…</p>}
          {listError && <p className="text-sm text-red-300">{listError}</p>}
          {!listLoading && !listError && flatFixtures.length === 0 && (
            <p className="rounded-lg border border-dashed border-slate-600 p-6 text-center text-sm text-slate-400">
              Nessuna partita eleggibile per {scanDate}. Esegui lo scan o cambia data.
            </p>
          )}
          <ul className="space-y-2">
            {flatFixtures.map(({ country, league, fixture: f }) => {
              const bm = f.bookmakers || {}
              const bmLabel = ['Bet365', 'Betfair', 'Pinnacle']
                .map((n) => `${n} ${bm[n] === 'OK' ? 'OK' : '—'}`)
                .join(' / ')
              const active = selectedId === f.id
              return (
                <li key={f.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(f.id)}
                    className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                      active
                        ? 'border-sky-500 bg-sky-950/40 text-white'
                        : 'border-slate-600 bg-slate-900/40 text-slate-200 hover:border-slate-500'
                    }`}
                  >
                    <span className="font-mono text-sky-300">{formatKickoffTime(f.kickoff)}</span>
                    {' — '}
                    <span className="font-medium">
                      {f.home_team_name} vs {f.away_team_name}
                    </span>
                    <span className="mt-1 block text-xs text-slate-400">
                      {country} · {league} — {bmLabel} — Statistiche {f.stats_status === 'ok' ? 'OK' : '—'}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>

        <section>
          <h2 className="mb-3 text-lg font-semibold text-white">Dettaglio analisi</h2>
          {selectedId == null && (
            <p className="text-sm text-slate-400">Seleziona una partita dalla lista.</p>
          )}
          {detailLoading && <p className="text-sm text-slate-400">Caricamento dettaglio…</p>}
          {detailError && <p className="text-sm text-red-300">{detailError}</p>}
          {detail && !detailLoading && <CecchinoTodayDetailPanel detail={detail} />}
        </section>
      </div>
    </div>
  )
}
