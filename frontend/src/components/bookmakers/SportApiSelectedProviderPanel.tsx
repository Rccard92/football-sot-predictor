import { useMemo, useState } from 'react'
import {
  postSyncSportApiProviderDetail,
  SPORTAPI_DEFAULT_PROVIDER_SLUG,
  type SportApiOddsProviderRow,
} from '../../lib/api'

const DEFAULT_SLUG = SPORTAPI_DEFAULT_PROVIDER_SLUG

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

export function SportApiSelectedProviderPanel({
  providers,
  onRefresh,
}: {
  providers: SportApiOddsProviderRow[]
  onRefresh?: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rawOpen, setRawOpen] = useState(false)
  const [detailRaw, setDetailRaw] = useState<unknown>(null)

  const row = useMemo(
    () => providers.find((p) => p.provider_slug === DEFAULT_SLUG) ?? providers.find((p) => p.is_selected),
    [providers],
  )

  const runDetail = async () => {
    setBusy(true)
    setError(null)
    try {
      const out = await postSyncSportApiProviderDetail(DEFAULT_SLUG, { timeoutMs: 90_000 })
      setDetailRaw(out.raw)
      onRefresh?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (!row) {
    return (
      <section className="rounded-2xl border border-violet-200/80 bg-violet-50/40 p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-violet-950">Provider selezionato — Sisal</h2>
        <p className="mt-2 text-xs text-slate-600">
          Sisal ({DEFAULT_SLUG}) non ancora in DB. Sincronizza la lista IT/app e poi «Aggiorna
          dettaglio Sisal».
        </p>
        <button
          type="button"
          onClick={() => void runDetail()}
          disabled={busy}
          className="mt-3 rounded-lg bg-violet-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-600 disabled:opacity-50"
        >
          {busy ? 'Sync…' : 'Aggiorna dettaglio Sisal'}
        </button>
        {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
      </section>
    )
  }

  return (
    <section className="rounded-2xl border border-violet-200/80 bg-violet-50/40 p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-violet-950">Provider selezionato — {row.provider_name}</h2>
          <p className="mt-1 font-mono text-[10px] text-violet-800/90">{row.provider_slug}</p>
        </div>
        <button
          type="button"
          onClick={() => void runDetail()}
          disabled={busy}
          className="rounded-lg bg-violet-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-600 disabled:opacity-50"
        >
          {busy ? 'Sync…' : 'Aggiorna dettaglio'}
        </button>
      </div>

      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}

      <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <dt className="text-slate-500">oddsProvider.id</dt>
          <dd className="font-mono font-medium text-slate-900">{row.provider_id ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-slate-500">oddsFrom</dt>
          <dd className="font-mono text-slate-900">
            {row.odds_from_id ?? '—'}
            {row.odds_from_slug ? (
              <span className="block text-[10px] font-sans text-slate-600">{row.odds_from_slug}</span>
            ) : null}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">liveOddsFrom</dt>
          <dd className="font-mono text-slate-900">{row.live_odds_from_id ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-slate-500">working provider_id (test OK)</dt>
          <dd className="font-mono font-medium text-emerald-800">
            {row.working_odds_provider_id ?? '— (esegui test evento)'}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Ultimo sync dettaglio</dt>
          <dd>{formatSyncedAt(row.last_synced_at)}</dd>
        </div>
      </dl>

      <p className="mt-3 text-[10px] leading-relaxed text-slate-600">
        Per le quote evento SportAPI prova in ordine: oddsProvider.id → oddsFrom.id →
        liveOddsFrom.id. Il primo ID che restituisce quote viene salvato come working.
      </p>

      {detailRaw != null ? (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setRawOpen((o) => !o)}
            className="text-[11px] font-medium text-violet-800 underline"
          >
            {rawOpen ? 'Nascondi' : 'Mostra'} payload raw dettaglio
          </button>
          {rawOpen ? (
            <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-900 p-2 text-[10px] text-slate-100">
              {JSON.stringify(detailRaw, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
