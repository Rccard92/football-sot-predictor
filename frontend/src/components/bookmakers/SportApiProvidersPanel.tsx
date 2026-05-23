import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getSportApiProviders,
  postSyncSportApiProviderDetail,
  postSyncSportApiProviders,
  type SportApiOddsProviderRow,
} from '../../lib/api'

function formatSyncedAt(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('it-IT', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function SportApiProvidersPanel({
  onProvidersChange,
}: {
  onProvidersChange?: (rows: SportApiOddsProviderRow[]) => void
}) {
  const [rows, setRows] = useState<SportApiOddsProviderRow[]>([])
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncBusy, setSyncBusy] = useState(false)
  const [detailSlug, setDetailSlug] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [channel, setChannel] = useState<'app' | 'web'>('app')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getSportApiProviders()
      const list = data.providers ?? []
      setRows(list)
      setLastSyncedAt(data.last_synced_at ?? null)
      onProvidersChange?.(list)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [onProvidersChange])

  useEffect(() => {
    void load()
  }, [load])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rows
    return rows.filter(
      (r) =>
        r.provider_name.toLowerCase().includes(q) ||
        r.provider_slug.toLowerCase().includes(q),
    )
  }, [rows, search])

  const runSyncIt = async () => {
    setSyncBusy(true)
    setMsg(null)
    setError(null)
    try {
      const out = await postSyncSportApiProviders(
        { country: 'IT', channel },
        { timeoutMs: 120_000 },
      )
      setMsg(
        `IT/${channel}: recuperati ${out.fetched} · creati ${out.created} · aggiornati ${out.updated} · totale DB ${out.total_in_db}`,
      )
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSyncBusy(false)
    }
  }

  const runDetail = async (slug: string) => {
    setDetailSlug(slug)
    setError(null)
    try {
      await postSyncSportApiProviderDetail(slug, { timeoutMs: 90_000 })
      setMsg(`Dettaglio aggiornato: ${slug}`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setDetailSlug(null)
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Provider SportAPI (Italia)</h2>
          <p className="mt-1 max-w-2xl text-[11px] leading-relaxed text-slate-600">
            Sincronizza la lista bookmaker da SportAPI (mercato IT, canale app). Per ogni riga puoi
            aggiornare il dettaglio (id quote, oddsFrom, liveOddsFrom).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value as 'app' | 'web')}
            className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
            title="Canale SportAPI"
          >
            <option value="app">App</option>
            <option value="web">Web</option>
          </select>
          <button
            type="button"
            onClick={() => void runSyncIt()}
            disabled={syncBusy || loading}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {syncBusy ? 'Sync…' : 'Aggiorna provider Italia'}
          </button>
        </div>
      </div>

      <p className="mt-2 text-[10px] text-slate-500">
        Ultimo sync lista: {formatSyncedAt(lastSyncedAt)} · {rows.length} provider in DB
      </p>
      {msg ? <p className="mt-2 text-xs text-emerald-700">{msg}</p> : null}
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}

      <div className="mt-3 flex flex-wrap gap-2">
        <input
          type="search"
          placeholder="Cerca nome o slug…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="min-w-[12rem] flex-1 rounded-lg border border-slate-200 px-2 py-1 text-xs"
        />
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
        >
          Ricarica
        </button>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-[11px]">
          <thead>
            <tr className="border-b border-slate-100 text-slate-500">
              <th className="py-1 pr-2 font-medium">Nome</th>
              <th className="py-1 pr-2 font-medium">Slug</th>
              <th className="py-1 pr-2 font-medium">ID</th>
              <th className="py-1 pr-2 font-medium">oddsFrom</th>
              <th className="py-1 pr-2 font-medium">Working</th>
              <th className="py-1 font-medium" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="py-4 text-slate-500">
                  Caricamento…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-4 text-slate-500">
                  Nessun provider. Esegui sync IT/app.
                </td>
              </tr>
            ) : (
              filtered.map((r) => (
                <tr key={r.id} className="border-b border-slate-50">
                  <td className="py-1.5 pr-2 font-medium text-slate-900">
                    {r.provider_name}
                    {r.is_selected ? (
                      <span className="ml-1 rounded bg-violet-100 px-1 text-[9px] text-violet-800">
                        selezionato
                      </span>
                    ) : null}
                  </td>
                  <td className="py-1.5 pr-2 font-mono text-[10px] text-slate-600">{r.provider_slug}</td>
                  <td className="py-1.5 pr-2 text-slate-700">{r.provider_id ?? '—'}</td>
                  <td className="py-1.5 pr-2 text-slate-700">
                    {r.odds_from_id ?? '—'}
                    {r.odds_from_name ? (
                      <span className="block text-[9px] text-slate-500">{r.odds_from_name}</span>
                    ) : null}
                  </td>
                  <td className="py-1.5 pr-2 text-slate-700">{r.working_odds_provider_id ?? '—'}</td>
                  <td className="py-1.5 text-right">
                    <button
                      type="button"
                      onClick={() => void runDetail(r.provider_slug)}
                      disabled={detailSlug === r.provider_slug}
                      className="rounded border border-slate-200 px-2 py-0.5 text-[10px] hover:bg-slate-50 disabled:opacity-50"
                    >
                      {detailSlug === r.provider_slug ? '…' : 'Dettaglio'}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
