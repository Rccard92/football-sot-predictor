import { useCallback, useEffect, useState } from 'react'
import {
  DEFAULT_SEASON,
  getTrackedBettingPicks,
  postCreateTrackedPicksFromRound,
  postRefreshTrackedPickResults,
  type TrackedBettingPickRow,
  type TrackedBettingPicksSummary,
} from '../lib/api'
import { formatKickoffReport } from '../utils/sportApiLineupMeta'

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

function sotResult(p: TrackedBettingPickRow): string {
  if (p.result_total_sot != null) {
    const h = p.result_home_sot != null ? String(p.result_home_sot) : '—'
    const a = p.result_away_sot != null ? String(p.result_away_sot) : '—'
    return `${h}+${a} = ${p.result_total_sot.toFixed(1)}`
  }
  return '—'
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

export function BetMonitoring() {
  const [rows, setRows] = useState<TrackedBettingPickRow[]>([])
  const [summary, setSummary] = useState<TrackedBettingPicksSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [createBusy, setCreateBusy] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)

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

  const runRefreshResults = async () => {
    setRefreshBusy(true)
    setActionMsg(null)
    try {
      const out = await postRefreshTrackedPickResults(DEFAULT_SEASON, { timeoutMs: 300_000 })
      setActionMsg(
        `Aggiornate ${out.picks_updated} giocate su ${out.picks_checked} controllate` +
          (out.errors?.length ? ` · ${out.errors.length} errori` : ''),
      )
      await load()
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setRefreshBusy(false)
    }
  }

  const hasPicks = rows.length > 0

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-slate-900">Monitoraggio Giocate</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Pronostici definitivi (auto ~30 min pre-match) o ricostruiti dal turno. Risultati live e finali da
            API-Sports.
          </p>
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
            onClick={() => void runRefreshResults()}
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
            <table className="min-w-full text-left text-[11px] text-slate-800">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-2">Data/Ora</th>
                  <th className="px-3 py-2">Match</th>
                  <th className="px-3 py-2">Pick</th>
                  <th className="px-3 py-2">Tipo</th>
                  <th className="px-3 py-2">Origine</th>
                  <th className="px-3 py-2">Previsti</th>
                  <th className="px-3 py-2">SOT live/finali</th>
                  <th className="px-3 py-2">Risultato</th>
                  <th className="px-3 py-2">Stato partita</th>
                  <th className="px-3 py-2">Esito</th>
                  <th className="px-3 py-2">Aggiornato</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id} className="border-b border-slate-100 hover:bg-slate-50/50">
                    <td className="whitespace-nowrap px-3 py-2.5 tabular-nums">
                      {p.kickoff_at ? formatKickoffReport(p.kickoff_at) : '—'}
                    </td>
                    <td className="px-3 py-2.5 font-medium">{p.match_name}</td>
                    <td className="px-3 py-2.5">{p.suggested_pick ?? '—'}</td>
                    <td className="px-3 py-2.5">{p.pick_type_label}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={
                          p.is_backfilled
                            ? 'rounded bg-amber-100 px-1 py-0.5 text-[10px] text-amber-900'
                            : ''
                        }
                        title={p.backfill_warning ?? undefined}
                      >
                        {p.origin_label}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 tabular-nums font-semibold">
                      {p.predicted_total_sot != null ? p.predicted_total_sot.toFixed(2) : '—'}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="tabular-nums text-[10px]">{sotResult(p)}</div>
                      {p.live_hint_label ? (
                        <div className="text-[9px] text-sky-700">{p.live_hint_label}</div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2.5 tabular-nums text-[10px]">{liveScore(p)}</td>
                    <td className="px-3 py-2.5">
                      <span className="font-medium">{p.fixture_status ?? '—'}</span>
                      {p.elapsed != null ? (
                        <span className="text-slate-500"> · {p.elapsed}&apos;</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${statusClass(p.status)}`}
                      >
                        {STATUS_LABELS[p.status] ?? p.status}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-[10px] text-slate-500">
                      {p.updated_at ? formatKickoffReport(p.updated_at) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="space-y-3 md:hidden">
            {rows.map((p) => (
              <article key={p.id} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
                <p className="text-[10px] text-slate-500">{p.kickoff_at ? formatKickoffReport(p.kickoff_at) : ''}</p>
                <p className="font-semibold text-slate-900">{p.match_name}</p>
                <p className="mt-1 text-sm">{p.suggested_pick}</p>
                <p className="mt-2 text-[11px] text-slate-600">
                  {p.pick_type_label} · {p.origin_label} · Previsti {p.predicted_total_sot?.toFixed(2) ?? '—'}
                </p>
                <p className="mt-1 text-[10px] text-slate-500">
                  {p.fixture_status} {liveScore(p)} · {sotResult(p)}
                </p>
                {p.live_hint_label ? (
                  <p className="text-[10px] text-sky-700">{p.live_hint_label}</p>
                ) : null}
                <span
                  className={`mt-2 inline-block rounded-full border px-2 py-0.5 text-[10px] ${statusClass(p.status)}`}
                >
                  {STATUS_LABELS[p.status] ?? p.status}
                </span>
              </article>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
