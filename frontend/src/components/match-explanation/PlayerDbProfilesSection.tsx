import { Fragment, useCallback, useEffect, useState } from 'react'
import {
  DEFAULT_SEASON,
  getFixturePlayerProfiles,
  type PlayerProfilesLimit,
} from '../../lib/api'
import type { PlayerDbProfileRow, PlayerDbTeamSide } from '../../types/playerDbProfiles'
import { formatFetchError } from '../../utils/formatFetchError'

const LIMIT_OPTIONS: { value: PlayerProfilesLimit; label: string }[] = [
  { value: 5, label: 'Top 5' },
  { value: 10, label: 'Top 10' },
  { value: 15, label: 'Top 15' },
  { value: 25, label: 'Top 25' },
  { value: 'all', label: 'Tutti' },
]

const INTRO_NOTE =
  'Migliori profili giocatore nel Player DB, ordinati per impatto tiri. Con formazioni SportAPI e modello v2.0 il layer player può usare titolari e assenze; altrimenti modalità storica (top profili). Dettaglio in albero componenti e in Lineup Impact.'

const EMPTY_MSG =
  'Profili giocatori non disponibili. Esegui da Admin: 1. Aggiorna statistiche giocatori · 2. Calcola profili giocatori'

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

type BadgeTone = 'violet' | 'emerald' | 'amber' | 'rose' | 'slate'

function ProfileBadge({ children, tone }: { children: string; tone: BadgeTone }) {
  const map: Record<BadgeTone, string> = {
    violet: 'bg-violet-50 text-violet-800 border-violet-200',
    emerald: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    amber: 'bg-amber-50 text-amber-900 border-amber-200',
    rose: 'bg-rose-50 text-rose-800 border-rose-200',
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
  }
  return (
    <span className={`inline-flex rounded border px-1 py-px text-[9px] font-medium leading-tight ${map[tone]}`}>
      {children}
    </span>
  )
}

type BadgeItem = { label: string; tone: BadgeTone; priority: number }

function collectBadges(row: PlayerDbProfileRow, impactRank: number): BadgeItem[] {
  const items: BadgeItem[] = []
  if (row.shooting_impact_score != null && impactRank >= 1 && impactRank <= 3) {
    items.push({ label: 'Top shooter', tone: 'violet', priority: 1 })
  }
  if (row.shooting_impact_score == null) {
    items.push({ label: 'Profilo incompleto', tone: 'slate', priority: 2 })
  }
  if (row.reliability_score != null && row.reliability_score >= 80) {
    items.push({ label: 'Alta affidabilità', tone: 'emerald', priority: 3 })
  }
  if (row.reliability_score != null && row.reliability_score < 40) {
    items.push({ label: 'Campione basso', tone: 'rose', priority: 4 })
  }
  if (row.recent_minutes_last5 != null && row.recent_minutes_last5 < 90) {
    items.push({ label: 'Min. recenti bassi', tone: 'amber', priority: 5 })
  }
  items.sort((a, b) => a.priority - b.priority)
  return items.slice(0, 2)
}

function teamSubtitle(side: PlayerDbTeamSide): string {
  if (side.profiles_total === 0) return 'Nessun profilo nel Player DB'
  if (side.profiles_returned >= side.profiles_total) {
    return `Tutti i ${side.profiles_total} profili disponibili`
  }
  return `Top ${side.profiles_returned} su ${side.profiles_total} profili disponibili`
}

const PRIMARY_COLS: {
  label: string
  kind: ColKind
  get: (r: PlayerDbProfileRow) => number | null | undefined
}[] = [
  { label: 'Tiri/90', kind: 'per90', get: (r) => r.shots_total_per90 },
  { label: 'SOT/90', kind: 'per90', get: (r) => r.shots_on_per90 },
  { label: 'Quota SOT', kind: 'pct', get: (r) => r.team_sot_share },
  { label: 'Impact', kind: 'impact', get: (r) => r.shooting_impact_score },
  { label: 'Affidabilità', kind: 'reliability', get: (r) => r.reliability_score },
]

function ExpandedDetails({ row }: { row: PlayerDbProfileRow }) {
  const fields: { label: string; value: string }[] = [
    { label: 'Minuti', value: formatCell('int', row.minutes_total) },
    { label: 'Min. ultime 5', value: formatCell('int', row.recent_minutes_last5) },
    { label: 'Quota tiri', value: formatCell('pct', row.team_shots_share) },
    { label: 'Rating', value: formatCell('rating', row.avg_rating) },
    { label: 'Tiri totali', value: formatCell('int', row.shots_total) },
    { label: 'SOT totali', value: formatCell('int', row.shots_on) },
    {
      label: 'Precisione tiro',
      value: row.shot_accuracy != null ? fmtPctShare(row.shot_accuracy) : '—',
    },
  ]
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 px-3 py-2 text-[11px] sm:grid-cols-4">
      {fields.map((f) => (
        <div key={f.label}>
          <span className="text-slate-500">{f.label}</span>
          <span className="ml-1 font-medium tabular-nums text-slate-800">{f.value}</span>
        </div>
      ))}
    </div>
  )
}

function TeamProfilesTable({
  side,
  expandedIds,
  onToggleExpand,
}: {
  side: PlayerDbTeamSide
  expandedIds: Set<number>
  onToggleExpand: (apiPlayerId: number) => void
}) {
  let impactRank = 0
  const colCount = PRIMARY_COLS.length + 3

  return (
    <div className="w-full rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-900">{side.team_name}</h3>
        <p className="mt-0.5 text-xs font-medium text-slate-700">{teamSubtitle(side)}</p>
        <p className="mt-0.5 text-[11px] text-slate-500">
          Ordinati per impatto tiri · solo visualizzazione audit (non usati dal modello v1.1)
        </p>
      </div>

      {side.players.length === 0 ? (
        <p className="px-4 py-3 text-xs text-slate-500">Nessun profilo per questa squadra.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-[640px] w-full text-left text-xs text-slate-800">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/90 text-slate-600">
                <th className="sticky left-0 z-10 bg-slate-50/95 px-3 py-2 font-medium">Giocatore</th>
                <th className="px-3 py-2 font-medium">Ruolo</th>
                {PRIMARY_COLS.map((c) => (
                  <th key={c.label} className="px-3 py-2 font-medium whitespace-nowrap">
                    {c.label}
                  </th>
                ))}
                <th className="w-10 px-2 py-2" aria-label="Dettagli" />
              </tr>
            </thead>
            <tbody>
              {side.players.map((row) => {
                const displayRank = row.shooting_impact_score != null ? (impactRank += 1) : 0
                const badges = collectBadges(row, displayRank)
                const isOpen = expandedIds.has(row.api_player_id)
                return (
                  <Fragment key={row.api_player_id}>
                    <tr className="border-b border-slate-100 hover:bg-slate-50/50">
                      <td className="sticky left-0 z-10 bg-white px-3 py-2 align-middle">
                        <div className="min-w-[120px] max-w-[200px]">
                          <div className="font-medium leading-tight text-slate-900">{row.name}</div>
                          {badges.length > 0 ? (
                            <div className="mt-0.5 flex flex-wrap gap-0.5">
                              {badges.map((b) => (
                                <ProfileBadge key={b.label} tone={b.tone}>
                                  {b.label}
                                </ProfileBadge>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-slate-600">{row.position ?? '—'}</td>
                      {PRIMARY_COLS.map((c) => (
                        <td key={c.label} className="whitespace-nowrap px-3 py-2 tabular-nums">
                          {formatCell(c.kind, c.get(row))}
                        </td>
                      ))}
                      <td className="px-2 py-2 text-center">
                        <button
                          type="button"
                          className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                          aria-expanded={isOpen}
                          aria-label={isOpen ? 'Nascondi dettagli' : 'Mostra dettagli'}
                          onClick={() => onToggleExpand(row.api_player_id)}
                        >
                          {isOpen ? '−' : '+'}
                        </button>
                      </td>
                    </tr>
                    {isOpen ? (
                      <tr className="border-b border-slate-100 bg-slate-50/60">
                        <td colSpan={colCount}>
                          <ExpandedDetails row={row} />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function PlayerDbProfilesSection({
  fixtureId,
  season = DEFAULT_SEASON,
}: {
  fixtureId: number
  season?: number
}) {
  const [limitChoice, setLimitChoice] = useState<PlayerProfilesLimit>(5)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [home, setHome] = useState<PlayerDbTeamSide | null>(null)
  const [away, setAway] = useState<PlayerDbTeamSide | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  const toggleExpand = useCallback((apiPlayerId: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(apiPlayerId)) next.delete(apiPlayerId)
      else next.add(apiPlayerId)
      return next
    })
  }, [])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (home && away) setRefreshing(true)
      else setLoading(true)
      setError(null)
      try {
        const data = await getFixturePlayerProfiles(fixtureId, { season, limit: limitChoice })
        if (cancelled) return
        if (data.status !== 'success' || !data.home || !data.away) {
          setHome(null)
          setAway(null)
          setError(data.message || 'Impossibile caricare i profili giocatori.')
          return
        }
        setHome(data.home)
        setAway(data.away)
        setExpandedIds(new Set())
      } catch (e) {
        if (!cancelled) {
          if (!home || !away) {
            setHome(null)
            setAway(null)
          }
          setError(formatFetchError(e, `GET .../fixture/${fixtureId}/player-profiles`))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
          setRefreshing(false)
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keep previous data during limit refresh
  }, [fixtureId, season, limitChoice])

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
        <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{INTRO_NOTE}</p>
      </div>

      <div className="p-4">
        {!loading && !error && home && away && !isEmpty ? (
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[11px] text-slate-500">
              Scegli quanti profili mostrare per squadra (ordinati per impatto tiri).
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-medium text-slate-600">Mostra:</span>
              {LIMIT_OPTIONS.map((opt) => (
                <button
                  key={String(opt.value)}
                  type="button"
                  className={`rounded-lg border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    limitChoice === opt.value
                      ? 'border-slate-800 bg-slate-800 text-white'
                      : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                  }`}
                  onClick={() => setLimitChoice(opt.value)}
                  disabled={refreshing}
                >
                  {opt.label}
                </button>
              ))}
              {refreshing ? <span className="text-[11px] text-slate-500">Aggiornamento…</span> : null}
            </div>
          </div>
        ) : null}

        {loading ? (
          <p className="text-xs text-slate-500">Caricamento profili giocatori…</p>
        ) : error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">{error}</p>
        ) : isEmpty ? (
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">{EMPTY_MSG}</p>
        ) : home && away ? (
          <div className="flex flex-col gap-4">
            <TeamProfilesTable side={home} expandedIds={expandedIds} onToggleExpand={toggleExpand} />
            <TeamProfilesTable side={away} expandedIds={expandedIds} onToggleExpand={toggleExpand} />
          </div>
        ) : null}
      </div>
    </section>
  )
}
