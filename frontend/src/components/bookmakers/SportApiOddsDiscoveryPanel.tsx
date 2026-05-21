import { useState } from 'react'
import {
  postSportApiOddsDiscovery,
  type SportApiOddsDiscoveryResponse,
} from '../../lib/api'

export function SportApiOddsDiscoveryPanel({
  apiSportsBookmakersTotal,
}: {
  apiSportsBookmakersTotal: number
}) {
  const [fixtureId, setFixtureId] = useState('')
  const [apiFixtureId, setApiFixtureId] = useState('')
  const [sportapiEventId, setSportapiEventId] = useState('13980080')
  const [providerId, setProviderId] = useState('1')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SportApiOddsDiscoveryResponse | null>(null)

  const runTest = async () => {
    const fid = fixtureId.trim() ? Number(fixtureId) : null
    const afx = apiFixtureId.trim() ? Number(apiFixtureId) : null
    const eid = sportapiEventId.trim() ? Number(sportapiEventId) : null
    if (!fid && !afx && !eid) {
      setError('Inserisci Fixture ID, API Fixture ID oppure SportAPI Event ID.')
      return
    }
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const out = await postSportApiOddsDiscovery(
        {
          fixture_id: fid,
          api_fixture_id: afx,
          sportapi_event_id: eid,
          provider_id: Number(providerId) || 1,
          save_snapshot: true,
        },
        { timeoutMs: 90_000 },
      )
      setResult(out)
      if (out.message && out.markets_count === 0) {
        setError(out.message)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const comparison = result?.comparison

  return (
    <section className="rounded-2xl border border-violet-200/80 bg-violet-50/30 p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-violet-950">SportAPI Odds Discovery</h2>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
        Testa le quote disponibili da SportAPI per una singola partita e provider. Questa fonte non restituisce
        necessariamente una lista globale bookmaker, quindi viene analizzata per evento.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block text-[11px]">
          <span className="font-medium text-slate-700">Fixture ID (interno)</span>
          <input
            type="number"
            value={fixtureId}
            onChange={(e) => setFixtureId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            placeholder="es. 375"
          />
        </label>
        <label className="block text-[11px]">
          <span className="font-medium text-slate-700">API Fixture ID</span>
          <input
            type="number"
            value={apiFixtureId}
            onChange={(e) => setApiFixtureId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
        </label>
        <label className="block text-[11px]">
          <span className="font-medium text-slate-700">SportAPI Event ID</span>
          <input
            type="number"
            value={sportapiEventId}
            onChange={(e) => setSportapiEventId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            placeholder="13980080"
          />
        </label>
        <label className="block text-[11px]">
          <span className="font-medium text-slate-700">Provider ID</span>
          <input
            type="number"
            value={providerId}
            onChange={(e) => setProviderId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            min={1}
          />
        </label>
      </div>

      <button
        type="button"
        disabled={busy}
        onClick={() => void runTest()}
        className="mt-3 rounded-md border border-violet-400 bg-white px-3 py-1.5 text-[11px] font-medium text-violet-900 hover:bg-violet-100 disabled:opacity-50"
      >
        {busy ? 'Chiamata in corso…' : 'Testa quote SportAPI'}
      </button>

      {error ? (
        <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-800">
          {error}
        </p>
      ) : null}

      {result?.status === 'success' ? (
        <div className="mt-4 space-y-3">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-[11px] text-emerald-950">
            <p>
              <span className="font-semibold">event_id:</span> {result.sportapi_event_id} ·{' '}
              <span className="font-semibold">provider:</span> {result.provider_id}
            </p>
            <p className="mt-1">
              Mercati normalizzati: <strong>{result.markets_count ?? 0}</strong>
              {result.bookmakers_count != null ? (
                <>
                  {' '}
                  · Bookmaker deducibili: <strong>{result.bookmakers_count}</strong>
                </>
              ) : null}
            </p>
          </div>

          {result.normalized_markets && result.normalized_markets.length > 0 ? (
            <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
              <table className="min-w-full text-left text-[10px] text-slate-800">
                <thead>
                  <tr className="border-b bg-slate-50 text-[9px] font-semibold uppercase text-slate-500">
                    <th className="px-2 py-1.5">Mercato</th>
                    <th className="px-2 py-1.5">Bookmaker</th>
                    <th className="px-2 py-1.5">Esito</th>
                    <th className="px-2 py-1.5">Linea</th>
                    <th className="px-2 py-1.5">Quota</th>
                    <th className="px-2 py-1.5">Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {result.normalized_markets.map((row, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="px-2 py-1.5">{row.market_name ?? '—'}</td>
                      <td className="px-2 py-1.5">{row.bookmaker_name ?? '—'}</td>
                      <td className="px-2 py-1.5">{row.outcome_name ?? '—'}</td>
                      <td className="px-2 py-1.5">{row.line ?? '—'}</td>
                      <td className="px-2 py-1.5 tabular-nums">{row.price ?? '—'}</td>
                      <td className="px-2 py-1.5">{row.status ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-[11px] text-amber-800">
              Nessun mercato normalizzato. Apri il raw payload per ispezionare la struttura restituita da SportAPI.
            </p>
          )}

          <details className="rounded-lg border border-slate-200 bg-white px-3 py-2">
            <summary className="cursor-pointer text-[11px] font-medium text-slate-800">Raw payload</summary>
            <pre className="mt-2 max-h-96 overflow-auto text-[10px] text-slate-700">
              {JSON.stringify(result.raw_payload, null, 2)}
            </pre>
          </details>

          {comparison ? (
            <div className="rounded-lg border border-slate-200 bg-white px-3 py-3">
              <h3 className="text-[11px] font-semibold text-slate-900">Confronto fonti</h3>
              <ul className="mt-2 list-inside list-disc text-[11px] text-slate-700">
                <li>
                  API-Sports: bookmakers globali disponibili ={' '}
                  <strong>{comparison.api_sports_bookmakers_total ?? apiSportsBookmakersTotal}</strong>
                </li>
                <li>
                  SportAPI: mercati trovati su questa partita ={' '}
                  <strong>{comparison.sportapi_markets_on_event ?? result.markets_count}</strong>
                </li>
                <li>
                  SportAPI: bookmaker deducibili ={' '}
                  <strong>
                    {comparison.sportapi_bookmakers_deduced != null
                      ? comparison.sportapi_bookmakers_deduced
                      : '—'}
                  </strong>
                </li>
              </ul>
              <p className="mt-2 text-[10px] italic text-slate-600">{comparison.note}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
