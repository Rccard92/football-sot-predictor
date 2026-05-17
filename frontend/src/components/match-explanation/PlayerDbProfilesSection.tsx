import { useEffect, useState } from 'react'
import { DEFAULT_SEASON, getFixturePlayerProfiles } from '../../lib/api'
import type { PlayerDbProfileRow, PlayerDbTeamSide } from '../../types/playerDbProfiles'
import { formatFetchError } from '../../utils/formatFetchError'

function fmtNum(v: number | null | undefined, decimals: number): string {
  if (v == null) return '—'
  return v.toFixed(decimals)
}

function fmtPctShare(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function fmtInt(v: number | null | undefined): string {
  if (v == null) return '—'
  return String(Math.round(v))
}

type ColKind = 'int' | 'per90' | 'pct' | 'rating' | 'impact' | 'reliability'

function formatCell(kind: ColKind, v: number | null | undefined): string {
  switch (kind) {
    case 'int':
      return fmtInt(v)
    case 'per90':
      return fmtNum(v, 2)
    case 'pct':
      return fmtPctShare(v)
    case 'rating':
      return fmtNum(v, 2)
    case 'impact':
      return fmtNum(v, 1)
    case 'reliability':
      return fmtInt(v)
    default:
      return '—'
  }
}

function ProfileBadge({ children, tone }: { children: React.ReactNode; tone: 'violet' | 'emerald' | 'amber' | 'rose' }) {
  const map = {
    violet: 'bg-violet-50 text-violet-900 border-violet-200',
    emerald: 'bg-emerald-50 text-emerald-900 border-emerald-200',
    amber: 'bg-amber-50 text-amber-950 border-amber-200',
    rose: 'bg-rose-50 text-rose-900 border-rose-200',
  }
  return (
    <span className={`ml-1 inline-flex rounded border px-1 py-0 text-[9px] font-medium ${map[tone]}`}>
      {children}
    </span>
  )
}

function playerBadges(row: PlayerDbProfileRow, rankAmongImpact: number): React.ReactNode {
  const badges: React.ReactNode[] = []
  if (row.shooting_impact_score != null && rankAmongImpact >= 1 && rankAmongImpact <= 3) {
    badges.push(
      <ProfileBadge key="top" tone="violet">
        Top shooter
      </ProfileBadge>,
    )
  }
  if (row.reliability_score != null && row.reliability_score >= 80) {
    badges.push(
      <ProfileBadge key="rel" tone="emerald">
        Alta affidabilità
      </ProfileBadge>,
    )
  }
  if (row.reliability_score != null && row.reliability_score < 40) {
    badges.push(
      <ProfileBadge key="low" tone="rose">
        Campione basso
      </ProfileBadge>,
    )
  }
  if (row.recent_minutes_last5 != null && row.recent_minutes_last5 < 90) {
    badges.push(
      <ProfileBadge key="min" tone="amber">
        Minuti recenti bassi
      </ProfileBadge>,
    )
  }
  return badges
}

function TeamProfilesTable({ side }: { side: PlayerDbTeamSide }) {
  const cols: { label: string; kind: ColKind; get: (r: PlayerDbProfileRow) => number | null | undefined }[] = [
    { label: 'Minuti', kind: 'int', get: (r) => r.minutes_total },
    { label: 'Min. ultime 5', kind: 'int', get: (r) => r.recent_minutes_last5 },
    { label: 'Tiri/90', kind: 'per90', get: (r) => r.shots_total_per90 },
    { label: 'SOT/90', kind: 'per90', get: (r) => r.shots_on_per90 },
    { label: 'Quota tiri', kind: 'pct', get: (r) => r.team_shots_share },
    { label: 'Quota SOT', kind: 'pct', get: (r) => r.team_sot_share },
    { label: 'Rating', kind: 'rating', get: (r) => r.avg_rating },
    { label: 'Impact', kind: 'impact', get: (r) => r.shooting_impact_score },
    { label: 'Affidabilità', kind: 'reliability', get: (r) => r.reliability_score },
  ]

  let impactRank = 0

  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50/40 p-3">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{side.team_name}</h3>
        <p className="text-[11px] text-slate-500">
          {side.profiles_returned} / {side.profiles_total} profili
        </p>
      </div>
      {side.players.length === 0 ? (
        <p className="text-xs text-slate-500">Nessun profilo per questa squadra.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-[11px] text-slate-800">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="py-1.5 pr-2 font-medium">Giocatore</th>
                <th className="py-1.5 pr-2 font-medium">Ruolo</th>
                {cols.map((c) => (
                  <th key={c.label} className="py-1.5 pr-2 font-medium whitespace-nowrap">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {side.players.map((row) => {
                const displayRank = row.shooting_impact_score != null ? (impactRank += 1) : 0
                return (
                  <tr key={row.api_player_id} className="border-b border-slate-100 align-top">
                    <td className="py-1.5 pr-2">
                      <span className="font-medium text-slate-900">{row.name}</span>
                      <div className="mt-0.5 flex flex-wrap gap-0.5">
                        {playerBadges(row, displayRank)}
                      </div>
                    </td>
                    <td className="py-1.5 pr-2 text-slate-600">{row.position ?? '—'}</td>
                    {cols.map((c) => (
                      <td key={c.label} className="py-1.5 pr-2 tabular-nums whitespace-nowrap">
                        {formatCell(c.kind, c.get(row))}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const EMPTY_MSG =
  'Profili giocatori non disponibili. Esegui da Admin: 1. Aggiorna statistiche giocatori · 2. Calcola profili giocatori'

export function PlayerDbProfilesSection({
  fixtureId,
  season = DEFAULT_SEASON,
}: {
  fixtureId: number
  season?: number
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [home, setHome] = useState<PlayerDbTeamSide | null>(null)
  const [away, setAway] = useState<PlayerDbTeamSide | null>(null)
  const [qualityNote, setQualityNote] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await getFixturePlayerProfiles(fixtureId, { season, limit: 15 })
        if (cancelled) return
        if (data.status !== 'success' || !data.home || !data.away) {
          setHome(null)
          setAway(null)
          setError(data.message || 'Impossibile caricare i profili giocatori.')
          setQualityNote(null)
          return
        }
        setHome(data.home)
        setAway(data.away)
        setQualityNote(data.quality?.note ?? null)
        const totalPlayers = data.home.players.length + data.away.players.length
        if (totalPlayers === 0 && data.home.profiles_total === 0 && data.away.profiles_total === 0) {
          setError(null)
        }
      } catch (e) {
        if (!cancelled) {
          setHome(null)
          setAway(null)
          setError(formatFetchError(e, `GET .../fixture/${fixtureId}/player-profiles`))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [fixtureId, season])

  const isEmpty =
    !loading &&
    !error &&
    home &&
    away &&
    home.players.length === 0 &&
    away.players.length === 0 &&
    home.profiles_total === 0 &&
    away.profiles_total === 0

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-2.5">
        <h2 className="text-sm font-semibold tracking-tight text-slate-900">Player DB / Profili giocatori</h2>
        <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
          Dati aggregati dai match player stats. Al momento sono mostrati solo per audit e non modificano ancora la
          previsione.
        </p>
      </div>
      <div className="p-4">
        {loading ? (
          <p className="text-xs text-slate-500">Caricamento profili giocatori…</p>
        ) : error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">{error}</p>
        ) : isEmpty ? (
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">{EMPTY_MSG}</p>
        ) : home && away ? (
          <>
            <p className="mb-3 text-[11px] text-slate-600">
              Questi dati derivano da player_match_stats e player_season_profiles. Al momento sono solo informativi: non
              entrano ancora nella formula del modello v1.1.
            </p>
            {qualityNote ? <p className="mb-3 text-[10px] text-slate-500">{qualityNote}</p> : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <TeamProfilesTable side={home} />
              <TeamProfilesTable side={away} />
            </div>
          </>
        ) : null}
      </div>
    </section>
  )
}
