import { useCallback, useEffect, useState } from 'react'
import {
  debugSearchCecchinoToday,
  eligibilityStatusLabel,
  getCecchinoTodayExcluded,
  type CecchinoTodayDebugSearchResponse,
  type CecchinoTodayExcludedFixture,
  type CecchinoTodayExcludedResponse,
} from '../../lib/cecchinoTodayApi'
import { formatFetchError } from '../../utils/formatFetchError'
import { todayCard, todayCardPadding, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  selectedDay: string
  open: boolean
  onToggle: () => void
  onRegisterLoad?: (loader: (() => Promise<void>) | null) => void
}

export function CecchinoTodayExcludedPanel({
  selectedDay,
  open,
  onToggle,
  onRegisterLoad,
}: Props) {
  const [data, setData] = useState<CecchinoTodayExcludedResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQ, setSearchQ] = useState('')
  const [searchResult, setSearchResult] = useState<CecchinoTodayDebugSearchResponse | null>(null)

  const loadExcluded = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getCecchinoTodayExcluded({ date: selectedDay })
      setData(res)
    } catch (e) {
      setError(formatFetchError(e))
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [selectedDay])

  useEffect(() => {
    onRegisterLoad?.(loadExcluded)
    return () => onRegisterLoad?.(null)
  }, [loadExcluded, onRegisterLoad])

  const handleToggle = () => {
    const willOpen = !open
    onToggle()
    if (willOpen) {
      void loadExcluded()
    }
  }

  const runSearch = async () => {
    if (!searchQ.trim()) return
    setError(null)
    try {
      const res = await debugSearchCecchinoToday({ date: selectedDay, q: searchQ.trim() })
      setSearchResult(res)
    } catch (e) {
      setError(formatFetchError(e))
      setSearchResult(null)
    }
  }

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`}>
      <button
        type="button"
        onClick={handleToggle}
        className="flex w-full items-center justify-between text-left"
      >
        <h3 className={todaySectionTitle}>Debug partite escluse</h3>
        <span className="text-sm text-blue-600">{open ? 'Nascondi' : 'Mostra'}</span>
      </button>

      {open && (
        <>
          <div className="flex flex-wrap gap-2">
            <input
              type="search"
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              placeholder="Cerca squadra o campionato…"
              className="min-w-[200px] flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={() => void runSearch()}
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900"
            >
              Cerca
            </button>
            <button
              type="button"
              onClick={() => void loadExcluded()}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Aggiorna
            </button>
          </div>

          {error && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          )}

          {searchResult && (
            <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-3 text-sm">
              <p className="font-medium text-indigo-900">
                Ricerca &quot;{searchResult.query}&quot; — {searchResult.message ?? searchResult.match_type}
              </p>
              {(searchResult.results?.length ?? 0) > 0 && (
                <ul className="mt-2 space-y-2">
                  {searchResult.results.map((r, i) => (
                    <li key={i} className="text-xs text-slate-700">
                      {r.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {loading && <p className="text-sm text-slate-500">Caricamento escluse…</p>}

          {!loading && data && (
            <>
              <p className="text-xs text-slate-600">
                {data.total} escluse per {data.scan_date}
              </p>
              <div className="max-h-96 overflow-auto rounded-lg border border-slate-200">
                <table className="w-full min-w-[640px] text-left text-xs">
                  <thead className="sticky top-0 bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-2 py-2">Partita</th>
                      <th className="px-2 py-2">Motivo</th>
                      <th className="px-2 py-2">Book</th>
                      <th className="px-2 py-2">Stats</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.fixtures.map((f: CecchinoTodayExcludedFixture) => (
                      <ExcludedRow key={f.id} fixture={f} />
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </section>
  )
}

function ExcludedRow({ fixture }: { fixture: CecchinoTodayExcludedFixture }) {
  const bm = fixture.bookmaker_debug || {}
  const stats = fixture.stats_debug || {}
  const cec = fixture.cecchino_debug
  const kpi = fixture.kpi_debug
  const blocking = fixture.blocking_reasons ?? []
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50">
      <td className="px-2 py-2">
        <div className="font-medium text-slate-800">
          {fixture.home_team_name} vs {fixture.away_team_name}
        </div>
        <div className="text-slate-500">{fixture.league_name}</div>
      </td>
      <td className="px-2 py-2">
        <div className="font-medium text-slate-800">
          {eligibilityStatusLabel(fixture.eligibility_status)}
        </div>
        <div className="text-slate-500">{fixture.eligibility_reason}</div>
        {blocking.length > 0 && (
          <div className="mt-1 font-mono text-[10px] text-slate-500">{blocking.join(' · ')}</div>
        )}
        {cec && (cec.missing_picchetto_quotas?.length ?? 0) > 0 && (
          <div className="mt-1 text-[10px] text-amber-800">
            Picchetti: {cec.missing_picchetto_quotas?.join(', ')}
          </div>
        )}
        {kpi && (kpi.missing_rows?.length ?? 0) > 0 && (
          <div className="mt-1 text-[10px] text-amber-800">
            KPI: {kpi.missing_rows?.join(', ')}
          </div>
        )}
      </td>
      <td className="px-2 py-2 font-mono text-[10px]">
        B365:{bm.Bet365 ?? '—'} BF:{bm.Betfair ?? '—'} Pin:{bm.Pinnacle ?? '—'}
      </td>
      <td className="px-2 py-2 font-mono text-[10px]">
        {String(stats.status ?? '—')} h{String(stats.home_context_sample ?? '—')}/a
        {String(stats.away_context_sample ?? '—')}
      </td>
    </tr>
  )
}

/** Alias descrittivo — stesso componente accordion debug escluse. */
export const CecchinoExcludedDebugAccordion = CecchinoTodayExcludedPanel
