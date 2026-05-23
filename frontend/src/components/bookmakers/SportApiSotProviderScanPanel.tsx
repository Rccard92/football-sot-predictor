import { useEffect, useState } from 'react'
import {
  getSportApiProviders,
  postSportApiScanSotProviders,
  type SportApiOddsProviderRow,
  type SportApiScanSotProvidersResponse,
} from '../../lib/api'

export function SportApiSotProviderScanPanel() {
  const [eventId, setEventId] = useState('13980080')
  const [country, setCountry] = useState('IT')
  const [providerSlug, setProviderSlug] = useState('')
  const [providers, setProviders] = useState<SportApiOddsProviderRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SportApiScanSotProvidersResponse | null>(null)
  const [rawOpen, setRawOpen] = useState<Record<string, boolean>>({})

  const loadProviders = () => {
    void getSportApiProviders()
      .then((out) => setProviders(out.providers ?? []))
      .catch(() => setProviders([]))
  }

  useEffect(() => {
    loadProviders()
  }, [])

  const runScan = async () => {
    const eid = Number(eventId.trim())
    if (!eid) {
      setError('Inserisci un SportAPI event_id valido.')
      return
    }
    if (providers.length === 0) {
      setError(
        'Nessun provider caricato in DB. Vai alla sezione Provider SportAPI e clicca «Aggiorna provider Italia».',
      )
      return
    }
    setBusy(true)
    setError(null)
    setResult(null)
    setRawOpen({})
    try {
      const out = await postSportApiScanSotProviders(
        {
          sportapi_event_id: eid,
          country: country.trim() || 'IT',
          provider_slug: providerSlug.trim() || null,
        },
        { timeoutMs: 300_000 },
      )
      setResult(out)
      if (out.providers_scanned === 0 && out.message) {
        setError(null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const showZeroAlert =
    result != null &&
    result.providers_scanned === 0 &&
    (result.message || result.scan_status !== 'ok')

  return (
    <section className="rounded-2xl border border-indigo-200/80 bg-indigo-50/30 p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-indigo-950">Scansione mercati SOT</h2>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
        Controlla tutti i provider italiani salvati per trovare eventuali mercati SOT su un evento.
        Operazione manuale: può richiedere diversi minuti.
      </p>

      <p className="mt-2 rounded border border-indigo-100 bg-white/70 px-2 py-1.5 text-[11px] text-slate-700">
        Provider caricati in DB: <span className="font-semibold">{providers.length}</span>
        {providers.length === 0 ? (
          <span className="text-amber-800">
            {' '}
            — sincronizza prima dalla sezione «Provider SportAPI (Italia)».
          </span>
        ) : null}
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        <label className="block text-[11px]">
          <span className="font-medium text-slate-700">SportAPI Event ID</span>
          <input
            type="number"
            value={eventId}
            onChange={(e) => setEventId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
        </label>
        <label className="block text-[11px]">
          <span className="font-medium text-slate-700">Country</span>
          <input
            type="text"
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
        </label>
        <label className="block text-[11px] sm:col-span-2">
          <span className="font-medium text-slate-700">Provider</span>
          <select
            value={providerSlug}
            onChange={(e) => setProviderSlug(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          >
            <option value="">Tutti i provider IT</option>
            {providers.map((p) => (
              <option key={p.provider_slug} value={p.provider_slug}>
                {p.provider_name} ({p.provider_slug})
              </option>
            ))}
          </select>
        </label>
      </div>

      <button
        type="button"
        disabled={busy}
        onClick={() => void runScan()}
        className="mt-3 rounded-md border border-indigo-500 bg-white px-3 py-1.5 text-[11px] font-medium text-indigo-900 hover:bg-indigo-100 disabled:opacity-50"
      >
        {busy ? 'Scansione in corso…' : 'Scansiona provider per mercati SOT'}
      </button>

      {error ? (
        <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-800">
          {error}
        </p>
      ) : null}

      {showZeroAlert ? (
        <p className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[11px] text-amber-950">
          {result?.message ??
            'Nessun provider controllato. Controlla di aver sincronizzato i provider italiani.'}
        </p>
      ) : null}

      {result ? (
        <div className="mt-4 space-y-3">
          <div className="rounded-lg border border-indigo-200 bg-white/80 px-3 py-2 text-[11px] text-slate-700">
            <p>
              Caricati in DB:{' '}
              <span className="font-medium">{result.providers_in_db ?? providers.length}</span> ·
              Controllati: <span className="font-medium">{result.providers_scanned}</span> · Con
              quote: <span className="font-medium">{result.providers_with_odds}</span> · Con SOT:{' '}
              <span className="font-medium">{result.providers_with_sot}</span> · Errori:{' '}
              <span className="font-medium">{result.providers_errors}</span>
            </p>
            {result.providers_matching_country != null ? (
              <p className="mt-1 text-slate-500">
                Provider con country {result.country}: {result.providers_matching_country}
              </p>
            ) : null}
          </div>

          {result.message && result.providers_scanned > 0 ? (
            <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-900">
              {result.message}
            </p>
          ) : null}

          {result.rows.length > 0 ? (
            <div className="overflow-x-auto rounded border border-slate-200 bg-white">
              <table className="w-full min-w-[720px] border-collapse text-[10px]">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-left text-slate-600">
                    <th className="px-2 py-1.5">Provider</th>
                    <th className="px-2 py-1.5">Provider ID</th>
                    <th className="px-2 py-1.5">Mercati</th>
                    <th className="px-2 py-1.5">SOT</th>
                    <th className="px-2 py-1.5">Candidati</th>
                    <th className="px-2 py-1.5">Stato</th>
                    <th className="px-2 py-1.5">Raw</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((r) => {
                    const open = rawOpen[r.provider_slug]
                    const candidates =
                      r.sot_candidate_markets?.map((c) => c.market_name).join(', ') || '—'
                    return (
                      <tr key={r.provider_slug} className="border-b border-slate-100 align-top">
                        <td className="px-2 py-1.5">
                          <div className="font-medium text-slate-800">{r.provider_name}</div>
                          <div className="text-slate-500">{r.provider_slug}</div>
                        </td>
                        <td className="px-2 py-1.5">{r.working_provider_id ?? '—'}</td>
                        <td className="px-2 py-1.5">{r.markets_count}</td>
                        <td className="px-2 py-1.5">{r.has_sot_market ? 'Sì' : 'No'}</td>
                        <td className="px-2 py-1.5 max-w-[200px] truncate" title={candidates}>
                          {candidates}
                        </td>
                        <td className="px-2 py-1.5">
                          {r.status}
                          {r.error ? (
                            <div className="text-rose-700" title={r.error}>
                              {r.error.slice(0, 80)}
                            </div>
                          ) : null}
                        </td>
                        <td className="px-2 py-1.5">
                          {r.raw_payload ? (
                            <>
                              <button
                                type="button"
                                className="text-indigo-700 underline"
                                onClick={() =>
                                  setRawOpen((prev) => ({
                                    ...prev,
                                    [r.provider_slug]: !prev[r.provider_slug],
                                  }))
                                }
                              >
                                {open ? 'Chiudi' : 'Apri'}
                              </button>
                              {open ? (
                                <pre className="mt-1 max-h-32 overflow-auto rounded bg-slate-900 p-1 text-[9px] text-slate-100">
                                  {JSON.stringify(r.raw_payload, null, 2)}
                                </pre>
                              ) : null}
                            </>
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
