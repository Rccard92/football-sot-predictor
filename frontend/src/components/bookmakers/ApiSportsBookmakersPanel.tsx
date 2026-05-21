import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getAdminBookmakers,
  postSyncBookmakers,
  type OddsBookmakerRow,
} from '../../lib/api'

type SelectionFilter = 'all' | 'selected' | 'not_selected'

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

export function ApiSportsBookmakersPanel({
  onTotalsChange,
}: {
  onTotalsChange?: (total: number) => void
}) {
  const [rows, setRows] = useState<OddsBookmakerRow[]>([])
  const [total, setTotal] = useState(0)
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncBusy, setSyncBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<SelectionFilter>('all')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getAdminBookmakers()
      setRows(data.bookmakers ?? [])
      setTotal(data.total ?? 0)
      setLastSyncedAt(data.last_synced_at ?? null)
      onTotalsChange?.(data.total ?? 0)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [onTotalsChange])

  useEffect(() => {
    void load()
  }, [load])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (filter === 'selected' && !r.is_selected) return false
      if (filter === 'not_selected' && r.is_selected) return false
      if (q && !r.name.toLowerCase().includes(q)) return false
      return true
    })
  }, [rows, search, filter])

  const runSync = async () => {
    setSyncBusy(true)
    setSyncMsg(null)
    setError(null)
    try {
      const out = await postSyncBookmakers({ timeoutMs: 120_000 })
      setSyncMsg(
        `Recuperati ${out.fetched_count} · creati ${out.created_count} · aggiornati ${out.updated_count} · totale salvati ${out.total_saved}`,
      )
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSyncBusy(false)
    }
  }

  return (
    <section className="rounded-2xl border border-indigo-200/80 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-indigo-950">API-Sports Bookmakers</h2>
          <p className="mt-1 text-[11px] text-slate-600">
            Lista globale bookmaker da GET /odds/bookmakers (API-Football).
          </p>
        </div>
        <button
          type="button"
          disabled={syncBusy}
          onClick={() => void runSync()}
          className="rounded-md border border-indigo-300 bg-white px-3 py-1.5 text-[11px] font-medium text-indigo-900 hover:bg-indigo-50 disabled:opacity-50"
        >
          {syncBusy ? 'Aggiornamento…' : 'Aggiorna bookmakers'}
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-slate-600">
        <span>
          Totale salvati: <strong className="text-slate-900">{total}</strong>
        </span>
        <span>
          Ultimo aggiornamento: <strong className="text-slate-900">{formatSyncedAt(lastSyncedAt)}</strong>
        </span>
      </div>

      {syncMsg ? <p className="mt-2 text-[11px] text-emerald-800">{syncMsg}</p> : null}
      {error ? (
        <p className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-800">
          {error}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cerca per nome bookmaker…"
          className="min-w-[12rem] flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        />
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as SelectionFilter)}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        >
          <option value="all">Tutti</option>
          <option value="selected">Selezionati</option>
          <option value="not_selected">Non selezionati</option>
        </select>
      </div>

      {loading ? (
        <p className="mt-3 text-sm text-slate-500">Caricamento…</p>
      ) : rows.length === 0 ? (
        <p className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-4 text-sm text-slate-600">
          Nessun bookmaker sincronizzato. Clicca su Aggiorna bookmakers per recuperare la lista da API-Sports.
        </p>
      ) : filtered.length === 0 ? (
        <p className="mt-3 text-sm text-slate-600">Nessun bookmaker corrisponde ai filtri.</p>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-xl border border-slate-100">
          <table className="min-w-full text-left text-[11px] text-slate-800">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-3 py-2">ID provider</th>
                <th className="px-3 py-2">Nome bookmaker</th>
                <th className="px-3 py-2">Provider</th>
                <th className="px-3 py-2">Selezionato</th>
                <th className="px-3 py-2">Attivo</th>
                <th className="px-3 py-2">Ultimo aggiornamento</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50/50">
                  <td className="px-3 py-2.5 tabular-nums">{r.provider_bookmaker_id}</td>
                  <td className="px-3 py-2.5 font-medium">{r.name}</td>
                  <td className="px-3 py-2.5">{r.provider}</td>
                  <td className="px-3 py-2.5">
                    <span className="inline-block rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">
                      {r.is_selected ? 'Sì' : 'No'}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                        r.is_active
                          ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                          : 'border-slate-200 bg-slate-100 text-slate-600'
                      }`}
                    >
                      {r.is_active ? 'Sì' : 'No'}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-[10px] text-slate-600">{formatSyncedAt(r.last_synced_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
