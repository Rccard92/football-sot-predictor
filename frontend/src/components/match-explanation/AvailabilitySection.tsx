import { useEffect, useState } from 'react'
import { getFixtureAvailability } from '../../lib/api'
import type { AvailabilityPlayerRow, AvailabilityTeamSide } from '../../types/fixtureAvailability'
import { formatFetchError } from '../../utils/formatFetchError'

const INTRO_NOTE =
  'Indisponibilità da player_availability (injuries API, ingestion admin). Solo audit: nessun impatto sulla formula baseline_v1_1_sot in questo stage (penalità Player layer in step 8B).'

const EMPTY_MSG =
  'Nessun record di indisponibilità attivo per questa partita. Da Admin puoi cliccare «Aggiorna indisponibili» (injuries).'

function fmtNum(v: number | null | undefined, d: number): string {
  if (v == null) return '—'
  return v.toFixed(d)
}

function PlayersTable({ title, rows }: { title: string; rows: AvailabilityPlayerRow[] }) {
  if (rows.length === 0) {
    return <p className="text-[11px] text-slate-500">Nessun {title.toLowerCase()}.</p>
  }
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-600">{title}</p>
      <AvailabilityTable rows={rows} />
    </div>
  )
}

function AvailabilityTable({ rows }: { rows: AvailabilityPlayerRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full text-left text-[11px]">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            <th className="px-2 py-1.5 font-medium">Giocatore</th>
            <th className="px-2 py-1.5 font-medium">Status</th>
            <th className="px-2 py-1.5 font-medium">Tipo</th>
            <th className="px-2 py-1.5 font-medium">Motivo</th>
            <th className="px-2 py-1.5 font-medium">SOT/90</th>
            <th className="px-2 py-1.5 font-medium">Quota SOT</th>
            <th className="px-2 py-1.5 font-medium">Impact</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.api_player_id ?? r.player_name}-${i}`} className="border-t border-slate-100">
              <td className="px-2 py-1.5 font-medium text-slate-900">
                <span className="inline-flex flex-wrap items-center gap-1">
                  {r.player_name}
                  {r.is_top_shooter ? (
                    <span className="rounded border border-violet-200 bg-violet-50 px-1 py-px text-[9px] font-medium text-violet-800">
                      Top shooter
                    </span>
                  ) : null}
                  {r.high_impact ? (
                    <span className="rounded border border-amber-200 bg-amber-50 px-1 py-px text-[9px] font-medium text-amber-900">
                      Impatto alto
                    </span>
                  ) : null}
                  {r.profile_found === false ? (
                    <span className="rounded border border-slate-200 bg-slate-50 px-1 py-px text-[9px] font-medium text-slate-600">
                      Profilo non trovato
                    </span>
                  ) : null}
                </span>
              </td>
              <td className="px-2 py-1.5 text-slate-700">{r.availability_status}</td>
              <td className="px-2 py-1.5 text-slate-600">{r.availability_type ?? '—'}</td>
              <td className="px-2 py-1.5 text-slate-600">{r.reason ?? '—'}</td>
              <td className="px-2 py-1.5 tabular-nums">{fmtNum(r.shots_on_per90, 2)}</td>
              <td className="px-2 py-1.5 tabular-nums">
                {r.team_sot_share != null ? `${(r.team_sot_share * 100).toFixed(1)}%` : '—'}
              </td>
              <td className="px-2 py-1.5 tabular-nums">{fmtNum(r.shooting_impact_score, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TeamAvailabilityCard({ side }: { side: AvailabilityTeamSide }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/40 p-3">
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{side.team_name}</h3>
        <span className="text-[11px] text-slate-500">{side.unavailable_count} indisponibili</span>
      </div>
      <PlayersTable title="Indisponibili" rows={side.players} />
    </div>
  )
}

export function AvailabilitySection({ fixtureId }: { fixtureId: number }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notAvailable, setNotAvailable] = useState(false)
  const [home, setHome] = useState<AvailabilityTeamSide | null>(null)
  const [away, setAway] = useState<AvailabilityTeamSide | null>(null)
  const [qualityNote, setQualityNote] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      setNotAvailable(false)
      try {
        const data = await getFixtureAvailability(fixtureId)
        if (cancelled) return
        if (data.status === 'not_available_yet' || data.availability_available === false) {
          setNotAvailable(true)
          setHome(null)
          setAway(null)
          return
        }
        if (data.status !== 'ok' || !data.home || !data.away) {
          setError(data.message || 'Impossibile caricare le indisponibilità.')
          return
        }
        setHome(data.home)
        setAway(data.away)
        setQualityNote(data.quality?.note ?? null)
      } catch (e) {
        if (!cancelled) setError(formatFetchError(e, `GET .../fixture/${fixtureId}/availability`))
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
        <h2 className="text-sm font-semibold tracking-tight text-slate-900">Indisponibili / Availability</h2>
        <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{INTRO_NOTE}</p>
      </div>
      <div className="p-4">
        {loading ? (
          <p className="text-xs text-slate-500">Caricamento indisponibilità…</p>
        ) : error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">{error}</p>
        ) : notAvailable ? (
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">{EMPTY_MSG}</p>
        ) : home && away ? (
          <div className="flex flex-col gap-4">
            <TeamAvailabilityCard side={home} />
            <TeamAvailabilityCard side={away} />
            {qualityNote ? <p className="text-[10px] text-slate-500">{qualityNote}</p> : null}
          </div>
        ) : null}
      </div>
    </section>
  )
}
