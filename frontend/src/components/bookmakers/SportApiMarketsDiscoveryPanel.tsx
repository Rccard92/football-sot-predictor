import { useCallback, useEffect, useState } from 'react'
import {
  getSportApiMarketMappings,
  patchDeactivateSportApiMarketMapping,
  postSportApiMarketMapping,
  postSportApiMarketsDiscovery,
  SPORTAPI_DEFAULT_PROVIDER_SLUG,
  type SportApiMarketMappingRow,
  type SportApiMarketsDiscoveryResponse,
  type SportApiEventOddsMarket,
  type SportApiSotCandidateMarket,
} from '../../lib/api'

const MARKET_KEYS = [
  { value: 'match_total_sot', label: 'SOT totale partita' },
  { value: 'home_team_sot', label: 'SOT casa' },
  { value: 'away_team_sot', label: 'SOT ospite' },
  { value: 'player_sot', label: 'SOT giocatore' },
] as const

function formatOdd(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

function compactOutcomes(m: SportApiEventOddsMarket): string {
  const parts = (m.outcomes ?? []).slice(0, 6).map((o) => {
    const n = o.name ?? '?'
    const p = o.price != null ? formatOdd(o.price) : '—'
    return `${n} ${p}`
  })
  const more = (m.outcomes?.length ?? 0) > 6 ? ` (+${(m.outcomes?.length ?? 0) - 6})` : ''
  return parts.join(' · ') + more
}

function SaveMappingControls({
  marketName,
  marketId,
  defaultKey,
  saveBusy,
  onSave,
}: {
  marketName: string
  marketId?: string | null
  defaultKey: string
  saveBusy: string | null
  onSave: (name: string, key: string, id?: string | null) => Promise<void>
}) {
  const [selected, setSelected] = useState(defaultKey)
  const busyKey = `${marketName}:${selected}`
  return (
    <div className="flex flex-wrap items-center gap-1">
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        className="rounded border border-slate-300 px-1 py-0.5 text-[10px]"
      >
        {MARKET_KEYS.map((k) => (
          <option key={k.value} value={k.value}>
            {k.label}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={saveBusy === busyKey}
        onClick={() => void onSave(marketName, selected, marketId)}
        className="rounded border border-emerald-400 px-1.5 py-0.5 text-[10px] text-emerald-900 disabled:opacity-50"
      >
        {saveBusy === busyKey ? '…' : 'Salva'}
      </button>
    </div>
  )
}

export function SportApiMarketsDiscoveryPanel() {
  const [eventId, setEventId] = useState('13980080')
  const [providerId, setProviderId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SportApiMarketsDiscoveryResponse | null>(null)
  const [mappings, setMappings] = useState<SportApiMarketMappingRow[]>([])
  const [saveBusy, setSaveBusy] = useState<string | null>(null)
  const [rawOpen, setRawOpen] = useState<Record<string, boolean>>({})

  const loadMappings = useCallback(async () => {
    try {
      const out = await getSportApiMarketMappings(SPORTAPI_DEFAULT_PROVIDER_SLUG)
      setMappings(out.mappings ?? [])
    } catch {
      setMappings([])
    }
  }, [])

  useEffect(() => {
    void loadMappings()
  }, [loadMappings])

  const discover = async () => {
    const eid = Number(eventId.trim())
    if (!eid) {
      setError('Inserisci un SportAPI event_id valido.')
      return
    }
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const out = await postSportApiMarketsDiscovery(
        {
          sportapi_event_id: eid,
          provider_slug: SPORTAPI_DEFAULT_PROVIDER_SLUG,
          provider_id: providerId.trim() ? Number(providerId) : null,
        },
        { timeoutMs: 90_000 },
      )
      setResult(out)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const saveMapping = async (marketName: string, normalizedKey: string, marketId?: string | null) => {
    const key = `${marketName}:${normalizedKey}`
    setSaveBusy(key)
    setError(null)
    try {
      await postSportApiMarketMapping({
        provider_slug: SPORTAPI_DEFAULT_PROVIDER_SLUG,
        raw_market_name: marketName,
        normalized_market_key: normalizedKey,
        provider_id_used: result?.working_provider_id ?? null,
        raw_market_id: marketId ?? null,
      })
      await loadMappings()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaveBusy(null)
    }
  }

  const deactivate = async (id: number) => {
    setError(null)
    try {
      await patchDeactivateSportApiMarketMapping(id)
      await loadMappings()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <section className="rounded-2xl border border-teal-200/80 bg-teal-50/30 p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-teal-950">Discovery mercati SportAPI</h2>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
        Esplora tutti i mercati odds di un evento e individua candidati SOT. I mapping salvati servono al test
        quote SOT del prossimo turno. Solo informativo: nessun impatto su pronostici o monitoraggio.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
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
          <span className="font-medium text-slate-700">Provider ID (opzionale)</span>
          <input
            type="number"
            value={providerId}
            onChange={(e) => setProviderId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            placeholder="auto da DB"
          />
        </label>
        <div className="flex items-end">
          <button
            type="button"
            disabled={busy}
            onClick={() => void discover()}
            className="rounded-md border border-teal-500 bg-white px-3 py-1.5 text-[11px] font-medium text-teal-900 hover:bg-teal-100 disabled:opacity-50"
          >
            {busy ? 'Scoperta in corso…' : 'Scopri mercati'}
          </button>
        </div>
      </div>

      {error ? (
        <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-800">
          {error}
        </p>
      ) : null}

      {result?.status === 'success' ? (
        <div className="mt-4 space-y-4">
          <div className="rounded-lg border border-teal-200 bg-white/80 px-3 py-2 text-[11px] text-slate-700">
            <p>
              <span className="font-medium">Provider ID funzionante:</span>{' '}
              {result.working_provider_id ?? '—'}
            </p>
            <p>
              <span className="font-medium">Mercati:</span> {result.markets_count} ·{' '}
              <span className="font-medium">Candidati SOT:</span>{' '}
              {result.sot_candidates_count ?? result.sot_candidate_markets?.length ?? 0}
            </p>
          </div>

          <div>
            <h3 className="text-[11px] font-semibold text-slate-800">Possibili mercati SOT</h3>
            {result.sot_candidate_markets.length === 0 ? (
              <p className="mt-1 text-[11px] text-slate-500">Nessun candidato rilevato per keyword.</p>
            ) : (
              <div className="mt-2 overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-[10px]">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-slate-600">
                      <th className="py-1 pr-2">Mercato</th>
                      <th className="py-1 pr-2">Tipo ipotizzato</th>
                      <th className="py-1 pr-2">Linea</th>
                      <th className="py-1 pr-2">Over</th>
                      <th className="py-1 pr-2">Under</th>
                      <th className="py-1 pr-2">Conf.</th>
                      <th className="py-1">Azioni</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.sot_candidate_markets.map((c: SportApiSotCandidateMarket) => (
                      <tr key={c.market_name} className="border-b border-slate-100 align-top">
                        <td className="py-1.5 pr-2 font-medium text-slate-800">{c.market_name}</td>
                        <td className="py-1.5 pr-2">{c.suggested_market_key ?? '—'}</td>
                        <td className="py-1.5 pr-2">{c.line ?? '—'}</td>
                        <td className="py-1.5 pr-2">{formatOdd(c.over_odd)}</td>
                        <td className="py-1.5 pr-2">{formatOdd(c.under_odd)}</td>
                        <td className="py-1.5 pr-2">{c.mapping_confidence ?? '—'}</td>
                        <td className="py-1.5">
                          <SaveMappingControls
                            marketName={c.market_name}
                            marketId={c.market_id}
                            defaultKey={c.suggested_market_key ?? 'match_total_sot'}
                            saveBusy={saveBusy}
                            onSave={saveMapping}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div>
            <h3 className="text-[11px] font-semibold text-slate-800">Tutti i mercati ({result.markets_count})</h3>
            <div className="mt-2 max-h-80 overflow-y-auto overflow-x-auto rounded border border-slate-200 bg-white">
              <table className="w-full min-w-[520px] border-collapse text-[10px]">
                <thead className="sticky top-0 bg-slate-50">
                  <tr className="border-b border-slate-200 text-left text-slate-600">
                    <th className="px-2 py-1">Nome</th>
                    <th className="px-2 py-1">Linea</th>
                    <th className="px-2 py-1">Outcome</th>
                    <th className="px-2 py-1">Raw</th>
                  </tr>
                </thead>
                <tbody>
                  {result.normalized_markets.map((m, idx) => {
                    const key = m.market_name || `market-${idx}`
                    const open = rawOpen[key]
                    return (
                      <tr key={key} className="border-b border-slate-100 align-top">
                        <td className="px-2 py-1 font-medium">{m.market_name}</td>
                        <td className="px-2 py-1">{m.line ?? '—'}</td>
                        <td className="px-2 py-1 text-slate-600">{compactOutcomes(m)}</td>
                        <td className="px-2 py-1">
                          <button
                            type="button"
                            className="text-teal-700 underline"
                            onClick={() => setRawOpen((prev) => ({ ...prev, [key]: !prev[key] }))}
                          >
                            {open ? 'Chiudi' : 'Apri'}
                          </button>
                          {open ? (
                            <pre className="mt-1 max-h-32 overflow-auto rounded bg-slate-900 p-1 text-[9px] text-slate-100">
                              {JSON.stringify(m.raw_market, null, 2)}
                            </pre>
                          ) : null}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {result.raw_payload ? (
            <details className="text-[10px]">
              <summary className="cursor-pointer font-medium text-slate-700">Payload grezzo evento (troncabile)</summary>
              <pre className="mt-1 max-h-48 overflow-auto rounded bg-slate-900 p-2 text-slate-100">
                {JSON.stringify(result.raw_payload, null, 2).slice(0, 12000)}
                {JSON.stringify(result.raw_payload).length > 12000 ? '\n… (troncato)' : ''}
              </pre>
            </details>
          ) : null}
        </div>
      ) : null}

      <div className="mt-6">
        <h3 className="text-[11px] font-semibold text-slate-800">Mapping salvati</h3>
        {mappings.length === 0 ? (
          <p className="mt-1 text-[11px] text-slate-500">Nessun mapping attivo.</p>
        ) : (
          <table className="mt-2 w-full border-collapse text-[10px]">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-600">
                <th className="py-1 pr-2">Mercato raw</th>
                <th className="py-1 pr-2">Chiave</th>
                <th className="py-1 pr-2">Conf.</th>
                <th className="py-1">Azioni</th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((row) => (
                <tr key={row.id} className="border-b border-slate-100">
                  <td className="py-1 pr-2">{row.raw_market_name}</td>
                  <td className="py-1 pr-2">{row.normalized_market_key}</td>
                  <td className="py-1 pr-2">{row.confidence}</td>
                  <td className="py-1">
                    <button
                      type="button"
                      onClick={() => void deactivate(row.id)}
                      className="text-rose-700 underline"
                    >
                      Disattiva
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
