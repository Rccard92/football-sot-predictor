import { useEffect, useState } from 'react'
import { getFixtureLineups } from '../../lib/api'
import type { LineupPlayerRow, LineupTeamSide } from '../../types/fixtureLineups'
import { formatFetchError } from '../../utils/formatFetchError'

const INTRO_NOTE =
  'Formazioni ufficiali da fixture_lineups (ingestion admin). Quando casa e trasferta sono disponibili, il Player layer v1.1 passa in modalità lineup-adjusted (nessuna API live in generazione predizioni).'

const EMPTY_MSG =
  'Formazioni ufficiali non ancora disponibili. Di solito vengono recuperate vicino all’inizio della partita. Da Admin puoi cliccare «Aggiorna formazioni ufficiali».'

function fmtNum(v: number | null | undefined, d: number): string {
  if (v == null) return '—'
  return v.toFixed(d)
}

function PlayersTable({ title, rows }: { title: string; rows: LineupPlayerRow[] }) {
  if (rows.length === 0) {
    return <p className="text-[11px] text-slate-500">Nessun {title.toLowerCase()}.</p>
  }
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-600">{title}</p>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-left text-[11px]">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-2 py-1.5 font-medium">#</th>
              <th className="px-2 py-1.5 font-medium">Giocatore</th>
              <th className="px-2 py-1.5 font-medium">Ruolo</th>
              <th className="px-2 py-1.5 font-medium">SOT/90</th>
              <th className="px-2 py-1.5 font-medium">Tiri/90</th>
              <th className="px-2 py-1.5 font-medium">Impact</th>
              <th className="px-2 py-1.5 font-medium">Aff.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.api_player_id ?? r.player_name}-${i}`} className="border-t border-slate-100">
                <td className="px-2 py-1.5 text-slate-700">{r.number ?? '—'}</td>
                <td className="px-2 py-1.5 font-medium text-slate-900">
                  <span className="inline-flex flex-wrap items-center gap-1">
                    {r.player_name}
                    {r.is_top_shooter_starter ? (
                      <span className="rounded border border-violet-200 bg-violet-50 px-1 py-px text-[9px] font-medium text-violet-800">
                        Top shooter
                      </span>
                    ) : null}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-slate-600">{r.position ?? '—'}</td>
                <td className="px-2 py-1.5 tabular-nums">{fmtNum(r.shots_on_per90, 2)}</td>
                <td className="px-2 py-1.5 tabular-nums">{fmtNum(r.shots_total_per90, 2)}</td>
                <td className="px-2 py-1.5 tabular-nums">{fmtNum(r.shooting_impact_score, 1)}</td>
                <td className="px-2 py-1.5 tabular-nums">{r.reliability_score ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TeamLineupCard({ side }: { side: LineupTeamSide }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/40 p-3">
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{side.team_name}</h3>
        {side.formation ? (
          <span className="rounded border border-slate-200 bg-white px-2 py-0.5 text-[11px] text-slate-700">
            {side.formation}
          </span>
        ) : null}
        {side.coach_name ? (
          <span className="text-[11px] text-slate-500">Allenatore: {side.coach_name}</span>
        ) : null}
      </div>
      <div className="space-y-4">
        <PlayersTable title="Titolari" rows={side.starters} />
        <PlayersTable title="Panchina" rows={side.substitutes} />
      </div>
    </div>
  )
}

export function LineupsSection({ fixtureId }: { fixtureId: number }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notAvailable, setNotAvailable] = useState(false)
  const [home, setHome] = useState<LineupTeamSide | null>(null)
  const [away, setAway] = useState<LineupTeamSide | null>(null)
  const [qualityNote, setQualityNote] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      setNotAvailable(false)
      try {
        const data = await getFixtureLineups(fixtureId)
        if (cancelled) return
        if (data.status === 'not_available_yet' || data.lineups_available === false) {
          setNotAvailable(true)
          setHome(null)
          setAway(null)
          return
        }
        if (data.status !== 'success' || !data.home || !data.away) {
          setError(data.message || 'Impossibile caricare le formazioni.')
          return
        }
        setHome(data.home)
        setAway(data.away)
        setQualityNote(data.quality?.note ?? null)
      } catch (e) {
        if (!cancelled) setError(formatFetchError(e, `GET .../fixture/${fixtureId}/lineups`))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [fixtureId])

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-2.5">
        <h2 className="text-sm font-semibold tracking-tight text-slate-900">Lineups / Formazioni ufficiali</h2>
        <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{INTRO_NOTE}</p>
      </div>
      <div className="p-4">
        {loading ? (
          <p className="text-xs text-slate-500">Caricamento formazioni…</p>
        ) : error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">{error}</p>
        ) : notAvailable ? (
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">{EMPTY_MSG}</p>
        ) : home && away ? (
          <div className="flex flex-col gap-4">
            <TeamLineupCard side={home} />
            <TeamLineupCard side={away} />
            {qualityNote ? <p className="text-[10px] text-slate-500">{qualityNote}</p> : null}
          </div>
        ) : null}
      </div>
    </section>
  )
}
