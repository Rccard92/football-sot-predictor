import { useCallback, useEffect, useState } from 'react'
import {
  DEFAULT_SEASON,
  getTrackedBettingPicks,
  postRefreshTrackedPickResults,
  type TrackedBettingPickRow,
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

function sotResult(p: TrackedBettingPickRow): string {
  if (p.result_total_sot != null) {
    const h = p.result_home_sot != null ? String(p.result_home_sot) : '—'
    const a = p.result_away_sot != null ? String(p.result_away_sot) : '—'
    return `${h}+${a} = ${p.result_total_sot.toFixed(1)}`
  }
  return '—'
}

export function BetMonitoring() {
  const [rows, setRows] = useState<TrackedBettingPickRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getTrackedBettingPicks(DEFAULT_SEASON)
      setRows(data.picks ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const runRefreshResults = async () => {
    setRefreshBusy(true)
    setRefreshMsg(null)
    try {
      const out = await postRefreshTrackedPickResults(DEFAULT_SEASON, { timeoutMs: 300_000 })
      setRefreshMsg(
        `Aggiornate ${out.picks_updated} giocate su ${out.picks_checked} controllate` +
          (out.errors?.length ? ` · ${out.errors.length} errori` : ''),
      )
      await load()
    } catch (e) {
      setRefreshMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setRefreshBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-slate-900">Monitoraggio Giocate</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Pronostici definitivi salvati automaticamente circa 30 minuti prima del calcio d&apos;inizio. I risultati
            live e finali arrivano da API-Sports (non SportAPI).
          </p>
        </div>
        <button
          type="button"
          disabled={refreshBusy}
          onClick={() => void runRefreshResults()}
          className="rounded-md border border-indigo-300 bg-white px-3 py-1.5 text-sm font-medium text-indigo-900 hover:bg-indigo-50 disabled:opacity-50"
        >
          {refreshBusy ? 'Aggiornamento…' : 'Aggiorna risultati'}
        </button>
      </div>
      {refreshMsg ? <p className="text-sm text-slate-700">{refreshMsg}</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {loading ? (
        <p className="text-sm text-slate-500">Caricamento…</p>
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          Nessuna giocata tracciata. Il job pre-match creerà i pick per le partite in finestra kickoff.
        </p>
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
                  <th className="px-3 py-2">Formazione</th>
                  <th className="px-3 py-2">Previsti</th>
                  <th className="px-3 py-2">Live/Finale</th>
                  <th className="px-3 py-2">Risultato</th>
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
                    <td className="px-3 py-2.5">{p.origin_label}</td>
                    <td className="max-w-[10rem] px-3 py-2.5 text-[10px] leading-snug" title={p.formation_label}>
                      {p.lineup_confirmed ? 'Ufficiale' : 'Probabile'}
                    </td>
                    <td className="px-3 py-2.5 tabular-nums font-semibold">
                      {p.predicted_total_sot != null ? p.predicted_total_sot.toFixed(2) : '—'}
                    </td>
                    <td className="px-3 py-2.5">
                      <div>
                        <span className="font-medium">{p.fixture_status ?? '—'}</span>
                        {p.elapsed != null ? (
                          <span className="text-slate-500"> · {p.elapsed}&apos;</span>
                        ) : null}
                      </div>
                      <div className="text-[10px] text-slate-500">{liveScore(p)}</div>
                    </td>
                    <td className="px-3 py-2.5 tabular-nums text-[10px]">{sotResult(p)}</td>
                    <td className="px-3 py-2.5">
                      <span className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${statusClass(p.status)}`}>
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
                <p className="mt-1 text-[10px] text-slate-500">{p.formation_label}</p>
                <span className={`mt-2 inline-block rounded-full border px-2 py-0.5 text-[10px] ${statusClass(p.status)}`}>
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
