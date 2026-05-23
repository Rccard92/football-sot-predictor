import { useCallback, useEffect, useRef, useState } from 'react'
import {
  DEFAULT_SEASON,
  getTrackedBettingPicks,
  postCreateTrackedPicksFromRound,
  postRefreshTrackedPickResults,
  type TrackedBettingPickRow,
  type TrackedBettingPicksSummary,
} from '../lib/api'
import { formatKickoffReport } from '../utils/sportApiLineupMeta'
import {
  formatSotDisplay,
  isLiveFixture,
  LIVE_MONITOR_REFRESH_MS,
} from '../utils/monitoring'

const STATUS_LABELS: Record<string, string> = {
  pending: 'In attesa',
  live: 'Live',
  won: 'Vinta',
  lost: 'Persa',
  void: 'Void',
  unavailable: 'N/D',
}

function statusClass(status: string): string {
  if (status === 'won') return 'border-emerald-200 bg-emerald-50 text-emerald-900'
  if (status === 'lost') return 'border-rose-200 bg-rose-50 text-rose-900'
  if (status === 'live') return 'border-sky-200 bg-sky-50 text-sky-900'
  return 'border-slate-200 bg-slate-100 text-slate-700'
}

function liveScore(p: TrackedBettingPickRow): string {
  if (p.score_home != null && p.score_away != null) {
    return `${p.score_home}–${p.score_away}`
  }
  return '—'
}

function sortByKickoffAsc(rows: TrackedBettingPickRow[]): TrackedBettingPickRow[] {
  return [...rows].sort((a, b) => {
    const ta = a.kickoff_at ? new Date(a.kickoff_at).getTime() : Number.POSITIVE_INFINITY
    const tb = b.kickoff_at ? new Date(b.kickoff_at).getTime() : Number.POSITIVE_INFINITY
    if (ta !== tb) return ta - tb
    return a.id - b.id
  })
}

function formatLastRefreshed(iso: string | null): string {
  if (!iso) return ''
  try {
    return formatKickoffReport(iso)
  } catch {
    return iso
  }
}

function SummaryCards({ summary }: { summary: TrackedBettingPicksSummary | null }) {
  if (!summary) return null
  const winRateLabel =
    summary.win_rate != null
      ? `${(summary.win_rate * 100).toFixed(1)}%`
      : 'Win rate non disponibile.'
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
      {[
        ['Monitorate', summary.total],
        ['In attesa', summary.pending],
        ['Live', summary.live],
        ['Vinte', summary.won],
        ['Perse', summary.lost],
        ['N/D', summary.unavailable],
        ['Void', summary.void],
        ['Win rate', winRateLabel],
      ].map(([label, val]) => (
        <div key={String(label)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm">
          <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">{val}</p>
        </div>
      ))}
    </div>
  )
}

function PickBadges({ p }: { p: TrackedBettingPickRow }) {
  return (
    <span className="mt-1 flex flex-wrap gap-1">
      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
        {p.pick_type_label}
      </span>
      {p.source === 'auto_pre_match' ? (
        <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium text-violet-900">
          Auto pre-match
        </span>
      ) : p.is_backfilled ? (
        <span
          className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900"
          title={p.backfill_warning ?? undefined}
        >
          {p.origin_label}
        </span>
      ) : null}
      {p.lineup_confirmed ? (
        <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-900">
          Formazione ufficiale
        </span>
      ) : p.formation_label ? (
        <span
          className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-medium text-sky-900"
          title={p.formation_label}
        >
          Probabile pre-match
        </span>
      ) : null}
    </span>
  )
}

function SotCell({ p }: { p: TrackedBettingPickRow }) {
  const { main, hint, title } = formatSotDisplay(p)
  return (
    <div title={title}>
      <div className="tabular-nums text-xs">{main}</div>
      {hint ? <div className="text-[10px] text-sky-700">{hint}</div> : null}
    </div>
  )
}

export function BetMonitoring() {
  const [rows, setRows] = useState<TrackedBettingPickRow[]>([])
  const [summary, setSummary] = useState<TrackedBettingPicksSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [createBusy, setCreateBusy] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [lastResultsRefreshAt, setLastResultsRefreshAt] = useState<string | null>(null)
  const refreshBusyRef = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getTrackedBettingPicks(DEFAULT_SEASON)
      setRows(sortByKickoffAsc(data.picks ?? []))
      setSummary(data.summary ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const runRefreshResults = useCallback(
    async (scope: 'all' | 'live' | 'unfinished' = 'all') => {
      if (refreshBusyRef.current) return
      refreshBusyRef.current = true
      setRefreshBusy(true)
      if (scope === 'all') setActionMsg(null)
      try {
        const out = await postRefreshTrackedPickResults(DEFAULT_SEASON, { scope }, { timeoutMs: 300_000 })
        if (out.last_refreshed_at) {
          setLastResultsRefreshAt(out.last_refreshed_at)
        }
        if (scope === 'all') {
          setActionMsg(
            `Aggiornate ${out.picks_updated} giocate su ${out.picks_checked} controllate` +
              (out.errors?.length ? ` · ${out.errors.length} errori` : ''),
          )
        }
        await load()
      } catch (e) {
        if (scope === 'all') {
          setActionMsg(e instanceof Error ? e.message : String(e))
        }
      } finally {
        refreshBusyRef.current = false
        setRefreshBusy(false)
      }
    },
    [load],
  )

  useEffect(() => {
    const hasLive = rows.some(isLiveFixture)
    if (!hasLive || document.visibilityState === 'hidden') {
      return
    }
    const id = window.setInterval(() => {
      if (document.visibilityState === 'hidden' || refreshBusyRef.current) return
      void runRefreshResults('live')
    }, LIVE_MONITOR_REFRESH_MS)
    return () => window.clearInterval(id)
  }, [rows, runRefreshResults])

  const runCreateFromRound = async (force = false) => {
    setCreateBusy(true)
    setActionMsg(null)
    try {
      const out = await postCreateTrackedPicksFromRound(
        DEFAULT_SEASON,
        {
          round: 'current',
          model_id: 'baseline_v2_0_lineup_impact',
          pick_type: 'cautious',
          force,
        },
        { timeoutMs: 120_000 },
      )
      setActionMsg(
        `Turno: create ${out.created}, aggiornate ${out.updated}, saltate ${out.skipped} su ${out.fixtures_total} partite` +
          (out.errors?.length ? ` · ${out.errors.length} errori` : ''),
      )
      await load()
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setCreateBusy(false)
    }
  }

  const hasPicks = rows.length > 0
  const hasLiveRows = rows.some(isLiveFixture)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-slate-900">Monitoraggio Giocate</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Pronostici definitivi (auto ~30 min pre-match) o ricostruiti dal turno. Risultati live e finali da
            API-Sports.
          </p>
          {lastResultsRefreshAt ? (
            <p className="mt-1 text-xs text-slate-500">
              Ultimo aggiornamento risultati: {formatLastRefreshed(lastResultsRefreshAt)}
              {hasLiveRows ? ' · auto-refresh ogni 60s (partite live)' : ''}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={createBusy}
            onClick={() => void runCreateFromRound(hasPicks)}
            className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-900 hover:bg-emerald-100 disabled:opacity-50"
            title="Usa le predizioni già salvate per il turno corrente (incluse partite terminate)"
          >
            {createBusy
              ? 'Creazione…'
              : hasPicks
                ? 'Crea/aggiorna monitoraggio turno'
                : 'Crea monitoraggio turno'}
          </button>
          <button
            type="button"
            disabled={refreshBusy || !hasPicks}
            onClick={() => void runRefreshResults('all')}
            title={
              hasPicks
                ? 'Recupera score e SOT da API-Sports'
                : 'Crea prima le pick monitorate dal turno'
            }
            className="rounded-md border border-indigo-300 bg-white px-3 py-1.5 text-sm font-medium text-indigo-900 hover:bg-indigo-50 disabled:opacity-50"
          >
            {refreshBusy ? 'Aggiornamento…' : 'Aggiorna risultati'}
          </button>
        </div>
      </div>

      {actionMsg ? <p className="text-sm text-slate-700">{actionMsg}</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      {!loading && hasPicks ? <SummaryCards summary={summary} /> : null}

      {loading ? (
        <p className="text-sm text-slate-500">Caricamento…</p>
      ) : !hasPicks ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          <p>
            Nessuna giocata tracciata. Puoi crearle dal turno corrente usando le predizioni già disponibili,
            oppure attendere il job pre-match automatico.
          </p>
          <p className="mt-3 text-[11px] text-slate-500">
            «Aggiorna risultati» funziona solo dopo che esistono pick monitorate nel database.
          </p>
        </div>
      ) : (
        <>
          <div className="hidden overflow-x-auto md:block">
            <table className="min-w-full text-left text-sm text-slate-800">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Data/Ora</th>
                  <th className="px-4 py-3">Match</th>
                  <th className="px-4 py-3">Pick</th>
                  <th className="px-4 py-3">Previsti</th>
                  <th className="px-4 py-3">SOT live/finali</th>
                  <th className="px-4 py-3">Risultato</th>
                  <th className="px-4 py-3">Stato partita</th>
                  <th className="px-4 py-3">Esito</th>
                  <th className="px-4 py-3">Aggiornato</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const live = isLiveFixture(p)
                  return (
                    <tr
                      key={p.id}
                      className={`border-b border-slate-100 ${
                        live ? 'bg-sky-50/60 font-semibold hover:bg-sky-50/80' : 'hover:bg-slate-50/50'
                      }`}
                    >
                      <td className="whitespace-nowrap px-4 py-3 tabular-nums text-xs">
                        {p.kickoff_at ? formatKickoffReport(p.kickoff_at) : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span>{p.match_name}</span>
                          {live ? (
                            <span className="rounded bg-sky-600 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                              LIVE
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <div>{p.suggested_pick ?? '—'}</div>
                        <PickBadges p={p} />
                      </td>
                      <td className="px-4 py-3 tabular-nums font-semibold text-sm">
                        {p.predicted_total_sot != null ? p.predicted_total_sot.toFixed(2) : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <SotCell p={p} />
                      </td>
                      <td className={`px-4 py-3 tabular-nums text-sm ${live ? 'text-sky-900' : ''}`}>
                        {liveScore(p)}
                      </td>
                      <td className={`px-4 py-3 text-sm ${live ? 'text-sky-900' : ''}`}>
                        <span className="font-medium">{p.fixture_status ?? '—'}</span>
                        {p.elapsed != null ? (
                          <span className={live ? 'text-sky-800' : 'text-slate-500'}> · {p.elapsed}&apos;</span>
                        ) : null}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${statusClass(p.status)}`}
                        >
                          {STATUS_LABELS[p.status] ?? p.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {p.updated_at ? formatKickoffReport(p.updated_at) : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="space-y-3 md:hidden">
            {rows.map((p) => {
              const live = isLiveFixture(p)
              const sot = formatSotDisplay(p)
              return (
                <article
                  key={p.id}
                  className={`rounded-xl border p-3 shadow-sm ${
                    live ? 'border-sky-200 bg-sky-50/60' : 'border-slate-200 bg-white'
                  }`}
                >
                  <p className="text-xs text-slate-500">{p.kickoff_at ? formatKickoffReport(p.kickoff_at) : ''}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold text-slate-900">{p.match_name}</p>
                    {live ? (
                      <span className="rounded bg-sky-600 px-1.5 py-0.5 text-[10px] font-bold text-white">LIVE</span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-sm">{p.suggested_pick}</p>
                  <PickBadges p={p} />
                  <p className="mt-2 text-xs text-slate-600">
                    Previsti {p.predicted_total_sot?.toFixed(2) ?? '—'}
                  </p>
                  <p className={`mt-1 text-xs ${live ? 'font-semibold text-sky-900' : 'text-slate-500'}`}>
                    {p.fixture_status} {liveScore(p)} · {sot.main}
                  </p>
                  {sot.hint ? <p className="text-[10px] text-sky-700">{sot.hint}</p> : null}
                  <span
                    className={`mt-2 inline-block rounded-full border px-2 py-0.5 text-xs ${statusClass(p.status)}`}
                  >
                    {STATUS_LABELS[p.status] ?? p.status}
                  </span>
                </article>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
