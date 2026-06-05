import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getBookmakerFixtureRawOdds,
  type BookmakerFixtureRawOddsResponse,
} from '../../lib/api'

const BOOKMAKER_OPTIONS = [
  { id: 8, name: 'Bet365', key: 'bet365' },
  { id: 3, name: 'Betfair', key: 'betfair' },
  { id: 4, name: 'Pinnacle', key: 'pinnacle' },
] as const

type Props = {
  initialProviderFixtureId?: string
  autoFetch?: boolean
}

function marketBadgeClass(normalized: string): string {
  if (normalized === 'MATCH_WINNER_1X2') return 'bg-blue-100 text-blue-800'
  if (normalized === 'DOUBLE_CHANCE') return 'bg-violet-100 text-violet-800'
  if (normalized === 'OVER_UNDER_GOALS') return 'bg-emerald-100 text-emerald-800'
  return 'bg-slate-100 text-slate-700'
}

export function BookmakerFixtureRawOddsPanel({
  initialProviderFixtureId = '',
  autoFetch = false,
}: Props) {
  const [providerFixtureId, setProviderFixtureId] = useState(initialProviderFixtureId)
  const [selected, setSelected] = useState<Record<string, boolean>>({
    bet365: true,
    betfair: true,
    pinnacle: true,
  })
  const [result, setResult] = useState<BookmakerFixtureRawOddsResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copyMsg, setCopyMsg] = useState<string | null>(null)

  const selectedIds = useMemo(
    () =>
      BOOKMAKER_OPTIONS.filter((b) => selected[b.key])
        .map((b) => b.id)
        .join(','),
    [selected],
  )

  const load = useCallback(async () => {
    const pfid = providerFixtureId.trim()
    if (!pfid) {
      setError('Inserisci API-Football fixture ID')
      return
    }
    if (!selectedIds) {
      setError('Seleziona almeno un bookmaker')
      return
    }
    setBusy(true)
    setError(null)
    setCopyMsg(null)
    try {
      const out = await getBookmakerFixtureRawOdds({
        provider_fixture_id: Number(pfid),
        bookmaker_ids: selectedIds,
        include_raw: true,
      })
      setResult(out)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore recupero JSON')
      setResult(null)
    } finally {
      setBusy(false)
    }
  }, [providerFixtureId, selectedIds])

  useEffect(() => {
    if (!autoFetch || !initialProviderFixtureId.trim()) return
    const timer = window.setTimeout(() => {
      void load()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [autoFetch, initialProviderFixtureId, load])

  const exportPayload = useMemo(() => {
    if (!result) return null
    const wanted = new Set(selectedIds.split(',').map((x) => Number(x)))
    return {
      provider_source: result.provider_source,
      provider_fixture_id: result.provider_fixture_id,
      bookmakers_requested: result.bookmakers_requested.filter((b) => wanted.has(b.id)),
      bookmakers: result.bookmakers.filter((b) => wanted.has(b.bookmaker_id)),
      summary: result.summary,
      over_under_debug: result.over_under_debug,
    }
  }, [result, selectedIds])

  const jsonText = useMemo(
    () => (exportPayload ? JSON.stringify(exportPayload, null, 2) : ''),
    [exportPayload],
  )

  const handleCopy = async () => {
    if (!jsonText) return
    try {
      await navigator.clipboard.writeText(jsonText)
      setCopyMsg('JSON copiato')
      window.setTimeout(() => setCopyMsg(null), 2000)
    } catch {
      setCopyMsg('Copia non riuscita')
    }
  }

  const handleDownload = () => {
    if (!exportPayload || !result) return
    const blob = new Blob([jsonText], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `bookmaker-raw-odds-${result.provider_fixture_id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Debug fixture odds</h2>
      <p className="mt-1 text-xs text-slate-600">
        Recupera JSON raw API-Football filtrato su Bet365 (8), Betfair (3) e Pinnacle (4).
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="block text-xs text-slate-600">
          API-Football fixture ID
          <input
            type="number"
            value={providerFixtureId}
            onChange={(e) => setProviderFixtureId(e.target.value)}
            className="mt-1 block w-44 rounded border border-slate-300 px-2 py-1.5 text-sm"
            placeholder="es. 1520609"
          />
        </label>
        <div className="flex flex-wrap gap-3 text-xs text-slate-700">
          {BOOKMAKER_OPTIONS.map((b) => (
            <label key={b.key} className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={selected[b.key]}
                onChange={(e) => setSelected((s) => ({ ...s, [b.key]: e.target.checked }))}
              />
              {b.name}
            </label>
          ))}
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={busy}
          className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? 'Recupero…' : 'Recupera JSON'}
        </button>
      </div>

      {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
      {copyMsg ? <p className="mt-2 text-sm text-emerald-700">{copyMsg}</p> : null}

      {result && exportPayload ? (
        <div className="mt-6 space-y-6">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
            <p className="font-semibold text-slate-800">Summary</p>
            <ul className="mt-2 list-inside list-disc space-y-0.5">
              <li>Bookmaker trovati: {result.summary.bookmakers_found.join(', ') || '—'}</li>
              <li>Mercati: {result.summary.markets_found.join(', ') || '—'}</li>
              <li>1X2 trovato: {result.summary.match_winner_found ? 'sì' : 'no'}</li>
              <li>Over 1.5 trovato: {result.summary.over_1_5_found ? 'sì' : 'no'}</li>
              <li>Over 2.5 trovato: {result.summary.over_2_5_found ? 'sì' : 'no'}</li>
            </ul>
            {result.over_under_debug.over_1_5.raw_market_names.length > 0 ? (
              <p className="mt-2">
                Mercati raw Over 1.5: {result.over_under_debug.over_1_5.raw_market_names.join(', ')}
              </p>
            ) : null}
            {result.over_under_debug.over_2_5.raw_market_names.length > 0 ? (
              <p className="mt-1">
                Mercati raw Over 2.5: {result.over_under_debug.over_2_5.raw_market_names.join(', ')}
              </p>
            ) : null}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-600">
                  <th className="py-1 pr-2">Bookmaker</th>
                  <th className="py-1 pr-2">Mercato raw</th>
                  <th className="py-1 pr-2">Normalizzato</th>
                  <th className="py-1 pr-2">Value raw</th>
                  <th className="py-1 pr-2">Selection</th>
                  <th className="py-1 pr-2">Odd</th>
                </tr>
              </thead>
              <tbody>
                {result.bookmakers
                  .filter((b) => selectedIds.split(',').map(Number).includes(b.bookmaker_id))
                  .flatMap((bm) =>
                    (bm.markets.length ? bm.markets : [{ bet_id: '', raw_market_name: '—', normalized_market: 'UNKNOWN', values: [] }]).flatMap(
                      (mkt) =>
                        (mkt.values.length ? mkt.values : [{ raw_value: '—', normalized_selection: '', odd: null }]).map(
                          (v, vi) => (
                            <tr key={`${bm.bookmaker_id}-${mkt.bet_id}-${vi}`} className="border-t border-slate-100">
                              <td className="py-1 pr-2">{bm.bookmaker_name}</td>
                              <td className="py-1 pr-2">{mkt.raw_market_name}</td>
                              <td className="py-1 pr-2">
                                <span className={`rounded px-1 py-0.5 text-[10px] font-semibold ${marketBadgeClass(mkt.normalized_market)}`}>
                                  {mkt.normalized_market}
                                </span>
                              </td>
                              <td className="py-1 pr-2">{v.raw_value}</td>
                              <td className="py-1 pr-2">{v.normalized_selection || '—'}</td>
                              <td className="py-1 pr-2 tabular-nums">{v.odd ?? '—'}</td>
                            </tr>
                          ),
                        ),
                    ),
                  )}
              </tbody>
            </table>
          </div>

          <div>
            <div className="mb-2 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleCopy()}
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                Copia JSON
              </button>
              <button
                type="button"
                onClick={handleDownload}
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                Scarica JSON
              </button>
            </div>
            <pre className="max-h-96 overflow-auto rounded-lg border border-slate-200 bg-slate-900 p-3 text-[11px] text-slate-100">
              {jsonText}
            </pre>
          </div>
        </div>
      ) : null}
    </section>
  )
}
