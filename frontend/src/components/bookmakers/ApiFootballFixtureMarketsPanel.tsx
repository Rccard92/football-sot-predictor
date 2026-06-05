import { useState } from 'react'
import { getApiFootballFixtureMarketsDebug, type ApiFootballFixtureMarketsDebugResponse } from '../../lib/api'

const HIGHLIGHT_MARKETS = new Set([
  'MATCH_WINNER_1X2',
  'DOUBLE_CHANCE',
  'OVER_UNDER_GOALS',
])

function marketBadgeClass(normalized: string): string {
  if (normalized === 'MATCH_WINNER_1X2') return 'bg-blue-100 text-blue-800'
  if (normalized === 'DOUBLE_CHANCE') return 'bg-violet-100 text-violet-800'
  if (normalized === 'OVER_UNDER_GOALS') return 'bg-emerald-100 text-emerald-800'
  return 'bg-slate-100 text-slate-700'
}

export function ApiFootballFixtureMarketsPanel() {
  const [fixtureId, setFixtureId] = useState('')
  const [providerFixtureId, setProviderFixtureId] = useState('')
  const [result, setResult] = useState<ApiFootballFixtureMarketsDebugResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    const fid = fixtureId.trim() ? Number(fixtureId) : undefined
    const pfid = providerFixtureId.trim() ? Number(providerFixtureId) : undefined
    if (!fid && !pfid) {
      setError('Inserisci fixture_id o provider_fixture_id')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const out = await getApiFootballFixtureMarketsDebug({
        fixture_id: fid,
        provider_fixture_id: pfid,
      })
      setResult(out)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento mercati')
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Mercati fixture (API-Football)</h2>
      <p className="mt-1 text-xs text-slate-600">
        Debug raw mercati Bet365 (8), Betfair (3), Pinnacle (4) per una fixture. Evidenzia 1X2, Double
        Chance e Over/Under Goals.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="block text-xs text-slate-600">
          fixture_id (DB)
          <input
            type="number"
            value={fixtureId}
            onChange={(e) => setFixtureId(e.target.value)}
            className="mt-1 block w-36 rounded border border-slate-300 px-2 py-1.5 text-sm"
            placeholder="es. 1234"
          />
        </label>
        <label className="block text-xs text-slate-600">
          provider_fixture_id
          <input
            type="number"
            value={providerFixtureId}
            onChange={(e) => setProviderFixtureId(e.target.value)}
            className="mt-1 block w-36 rounded border border-slate-300 px-2 py-1.5 text-sm"
            placeholder="es. 867946"
          />
        </label>
        <button
          type="button"
          onClick={() => void load()}
          disabled={busy}
          className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? 'Caricamento…' : 'Carica mercati'}
        </button>
      </div>

      {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}

      {result ? (
        <div className="mt-4 space-y-6">
          <p className="text-xs text-slate-500">
            provider_fixture_id: {result.provider_fixture_id}
            {result.fixture_id != null ? ` · fixture_id: ${result.fixture_id}` : ''}
          </p>

          {result.detected_over_candidates && result.detected_over_candidates.length > 0 ? (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
                Over 1.5 / 2.5 rilevati
              </h3>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full min-w-[480px] border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-slate-600">
                      <th className="py-1 pr-2">Book</th>
                      <th className="py-1 pr-2">Mercato raw</th>
                      <th className="py-1 pr-2">Selection</th>
                      <th className="py-1 pr-2">Quota</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.detected_over_candidates.map((c, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="py-1 pr-2">{c.bookmaker_name}</td>
                        <td className="py-1 pr-2">{c.raw_market_name}</td>
                        <td className="py-1 pr-2">{c.raw_value}</td>
                        <td className="py-1 pr-2 tabular-nums">{c.odd ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-xs text-amber-700">Nessun candidato Over 1.5/2.5 rilevato nel payload.</p>
          )}

          {result.bookmakers?.map((bm) => (
            <div key={bm.bookmaker_id}>
              <h3 className="text-sm font-medium text-slate-800">
                {bm.bookmaker_name} (id {bm.bookmaker_id})
              </h3>
              {'error' in bm && bm.error ? (
                <p className="mt-1 text-xs text-red-600">{String(bm.error)}</p>
              ) : null}
              <div className="mt-2 space-y-3">
                {(bm.markets ?? []).map((mkt, idx) => (
                  <div
                    key={idx}
                    className={`rounded border p-2 ${
                      HIGHLIGHT_MARKETS.has(mkt.normalized_market)
                        ? 'border-indigo-200 bg-indigo-50/40'
                        : 'border-slate-100 bg-slate-50/50'
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-slate-800">{mkt.raw_market_name}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${marketBadgeClass(mkt.normalized_market)}`}>
                        {mkt.normalized_market}
                      </span>
                      {mkt.provider_market_id ? (
                        <span className="text-[10px] text-slate-500">bet id {mkt.provider_market_id}</span>
                      ) : null}
                    </div>
                    {mkt.values && mkt.values.length > 0 ? (
                      <ul className="mt-1 space-y-0.5 text-xs text-slate-700">
                        {mkt.values.map((v, vi) => (
                          <li key={vi} className="tabular-nums">
                            {v.raw_value}: {v.odd ?? '—'}
                            {v.normalized_selection && v.normalized_selection !== 'UNKNOWN' ? (
                              <span className="ml-1 text-slate-500">({v.normalized_selection})</span>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-xs text-slate-500">Nessun value</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}
