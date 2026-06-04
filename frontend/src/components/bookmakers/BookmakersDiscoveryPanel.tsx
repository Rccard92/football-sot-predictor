import { useCallback, useEffect, useState } from 'react'
import {
  getBookmakerDiscoveryMarkets,
  getBookmakerDiscoveryProviders,
  getCompetitionBookmakerCoverage,
  getUnifiedBookmakersList,
  postCompetitionSyncNextRoundOdds,
  postSyncBookmakers,
  postSyncSportApiProviders,
  type BookmakerCoverageResponse,
  type BookmakerProviderSourceRow,
} from '../../lib/api'
import { ApiSportsBookmakersPanel } from './ApiSportsBookmakersPanel'

function statusBadge(status: string) {
  if (status === 'available') {
    return <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">Disponibile</span>
  }
  if (status === 'not_configured') {
    return <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">Non configurato</span>
  }
  return <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-800">Errore</span>
}

export function BookmakersDiscoveryPanel({
  competitionId,
}: {
  competitionId: number | null
}) {
  const [sources, setSources] = useState<BookmakerProviderSourceRow[]>([])
  const [bookmakers, setBookmakers] = useState<Awaited<ReturnType<typeof getUnifiedBookmakersList>>['bookmakers']>([])
  const [markets, setMarkets] = useState<Awaited<ReturnType<typeof getBookmakerDiscoveryMarkets>>['markets']>([])
  const [coverage, setCoverage] = useState<BookmakerCoverageResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [prov, bm, mkt] = await Promise.all([
        getBookmakerDiscoveryProviders(),
        getUnifiedBookmakersList(),
        getBookmakerDiscoveryMarkets(),
      ])
      setSources(prov.sources ?? [])
      setBookmakers(bm.bookmakers ?? [])
      setMarkets(mkt.markets ?? [])
      if (competitionId) {
        const cov = await getCompetitionBookmakerCoverage(competitionId, {
          only_next_round: true,
          market: 'MATCH_WINNER_1X2',
        })
        setCoverage(cov)
      } else {
        setCoverage(null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [competitionId])

  useEffect(() => {
    let cancelled = false
    void Promise.resolve().then(async () => {
      if (cancelled) return
      await load()
    })
    return () => {
      cancelled = true
    }
  }, [load])

  const discoverBookmakers = async () => {
    setBusy('bookmakers')
    setMsg(null)
    setError(null)
    try {
      const af = sources.find((s) => s.provider_source === 'api_football')
      if (af?.status === 'available') {
        await postSyncBookmakers({ timeoutMs: 120_000 })
      }
      const sa = sources.find((s) => s.provider_source === 'sportapi')
      if (sa?.status === 'available') {
        await postSyncSportApiProviders({ country: 'IT', channel: 'app' })
      }
      setMsg('Sync bookmaker completato (fonti configurate).')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const sync1x2 = async () => {
    if (!competitionId) {
      setError('Seleziona una competizione dal banner contesto.')
      return
    }
    setBusy('sync1x2')
    setMsg(null)
    setError(null)
    try {
      const out = await postCompetitionSyncNextRoundOdds(
        competitionId,
        { market: 'MATCH_WINNER_1X2', provider_source: 'auto' },
        { timeoutMs: 300_000 },
      )
      setMsg(
        `Quote salvate: ${out.odds_saved}/${out.fixtures_checked} · bookmaker: ${(out.bookmakers_found ?? []).join(', ') || '—'}`,
      )
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Provider</h2>
        {loading && <p className="mt-2 text-sm text-slate-500">Caricamento…</p>}
        {!loading && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {sources.map((s) => (
              <div key={s.provider_source} className="rounded border border-slate-100 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-slate-800">{s.label}</span>
                  {statusBadge(s.status)}
                </div>
                <p className="mt-1 text-xs text-slate-600">
                  Bookmaker in DB: {s.bookmakers_count}
                  {s.last_synced_at ? ` · ultimo sync ${new Date(s.last_synced_at).toLocaleString('it-IT')}` : ''}
                </p>
                {s.note && <p className="mt-1 text-xs text-amber-800">{s.note}</p>}
              </div>
            ))}
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            disabled={!!busy}
            onClick={() => void discoverBookmakers()}
          >
            {busy === 'bookmakers' ? 'Sync…' : 'Scopri bookmakers'}
          </button>
          <button
            type="button"
            className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
            disabled={!!busy || !competitionId}
            onClick={() => void sync1x2()}
          >
            {busy === 'sync1x2' ? 'Sync quote…' : 'Sincronizza quote 1X2 (prossimo turno)'}
          </button>
        </div>
        {msg && <p className="mt-2 text-sm text-emerald-700">{msg}</p>}
        {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Lista bookmakers (unificata)</h2>
        <p className="text-xs text-slate-500">{bookmakers.length} voci</p>
        <div className="mt-2 max-h-48 overflow-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b text-slate-500">
                <th className="py-1 pr-2">Fonte</th>
                <th className="py-1 pr-2">Nome</th>
                <th className="py-1">ID</th>
              </tr>
            </thead>
            <tbody>
              {bookmakers.slice(0, 50).map((b, i) => (
                <tr key={`${b.provider_source}-${b.provider_bookmaker_id}-${i}`} className="border-b border-slate-50">
                  <td className="py-1 pr-2">{b.provider_source}</td>
                  <td className="py-1 pr-2">{b.name}</td>
                  <td className="py-1 font-mono text-slate-600">{b.provider_bookmaker_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Mercati normalizzati</h2>
        <div className="mt-2 max-h-40 overflow-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b text-slate-500">
                <th className="py-1 pr-2">Provider</th>
                <th className="py-1 pr-2">Nome</th>
                <th className="py-1">Normalizzato</th>
              </tr>
            </thead>
            <tbody>
              {markets.map((m, i) => (
                <tr
                  key={`${m.provider_source}-${m.market_name}-${i}`}
                  className={m.is_unknown ? 'bg-amber-50' : ''}
                >
                  <td className="py-1 pr-2">{m.provider_source}</td>
                  <td className="py-1 pr-2">{m.market_name}</td>
                  <td className="py-1 font-medium">{m.normalized_market}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Coverage 1X2 — prossimo turno</h2>
        {!competitionId && (
          <p className="mt-2 text-sm text-amber-800">Seleziona una competizione per vedere la coverage.</p>
        )}
        {coverage && (
          <>
            <p className="mt-2 text-sm text-slate-700">
              Turno: {coverage.round_label ?? '—'} · {coverage.fixtures_with_odds}/{coverage.fixtures_total}{' '}
              fixture con quote ({coverage.coverage_pct}%)
            </p>
            <ul className="mt-2 max-h-40 space-y-1 overflow-auto text-xs">
              {coverage.fixtures.map((f) => (
                <li key={f.fixture_id} className={f.has_odds ? 'text-slate-800' : 'text-slate-400'}>
                  {f.home_team} – {f.away_team}
                  {f.has_odds && f.sample_odds[0]
                    ? ` · ${f.sample_odds[0].home_odds}/${f.sample_odds[0].draw_odds}/${f.sample_odds[0].away_odds}`
                    : ' · senza quote'}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <ApiSportsBookmakersPanel />
    </div>
  )
}
