import type { LineupImpactSideSimulation, SportApiPlayerMatchRow } from '../types/lineupImpact'
import type { PlayerDbProfileRow } from '../types/playerDbProfiles'
import type { SportApiDisplayRole, SportApiLineupPlayer } from '../types/sportapi'
import { resolveTacticalLines, roleSortKey, tacticalLineIndexForPlayer } from './sportapiFormation'

export type StarterFieldForceRow = {
  provider_player_id: number
  name: string
  role: SportApiDisplayRole
  status: string
  status_note?: string
  sot_per_90: number | null
  shots_per_90: number | null
  team_sot_share_pct: number | null
  shooting_impact: number | null
  defensive_impact: number | null
  reliability: number | null
  tactical_line_index: number
  sort_impact: number
}

function matchRow(matching: SportApiPlayerMatchRow[] | undefined, providerId: number) {
  return matching?.find((m) => m.sportapi_player_id === providerId)
}

function impactForStarter(
  lineupSide: LineupImpactSideSimulation | undefined,
  providerId: number,
): { status: string; status_note?: string; sot_per_90: number | null; share_pct: number | null } {
  const top = lineupSide?.top_sot_players?.find((p) => p.sportapi_player_id === providerId)
  if (top) {
    return {
      status: top.status,
      status_note: top.status_note,
      sot_per_90: top.sot_per_90 ?? null,
      share_pct: top.team_sot_share_pct ?? (top.team_sot_share != null ? top.team_sot_share * 100 : null),
    }
  }
  return { status: 'STARTER', status_note: undefined, sot_per_90: null, share_pct: null }
}

function defensiveImpact(
  lineupSide: LineupImpactSideSimulation | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
  providerId: number,
): number | null {
  const m = matchRow(matching, providerId)
  const pid = m?.player_id
  if (pid == null) return null
  const d = lineupSide?.defensive_key_players?.find((p) => p.player_id === pid)
  return d?.defensive_importance ?? null
}

export function buildStarterFieldRows(
  formation: string | null | undefined,
  starters: SportApiLineupPlayer[],
  tacticalLinesFromApi: SportApiLineupPlayer[][] | undefined,
  lineupSide: LineupImpactSideSimulation | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
  profilesByApiId: Map<number, PlayerDbProfileRow>,
): StarterFieldForceRow[] {
  const lines = resolveTacticalLines(formation, starters, tacticalLinesFromApi)

  const rows: StarterFieldForceRow[] = starters.map((s) => {
    const role = (s.display_role || 'C') as SportApiDisplayRole
    const m = matchRow(matching, s.provider_player_id)
    const apiId = m?.api_sports_player_id ?? m?.player_id
    const prof = apiId != null ? profilesByApiId.get(Number(apiId)) : undefined
    const imp = impactForStarter(lineupSide, s.provider_player_id)

    let status = imp.status
    let statusNote = imp.status_note
    if (!m || m.recommendation !== 'AUTO_SAFE') {
      status = 'UNMAPPED'
      statusNote = statusNote ?? 'Mapping API-Sports assente o da revisionare'
    } else if (status === 'STARTER' && !imp.status_note) {
      statusNote = 'In formazione'
    }

    const sot =
      imp.sot_per_90 ??
      (prof?.shots_on_per90 != null ? Number(prof.shots_on_per90) : null)
    const shots =
      prof?.shots_on_per90 != null
        ? Number(prof.shots_on_per90)
        : prof?.shots_total_per90 != null
          ? Number(prof.shots_total_per90)
          : null
    const sharePct =
      imp.share_pct ??
      (prof?.team_sot_share != null ? Math.round(prof.team_sot_share * 1000) / 10 : null)

    const defImp = defensiveImpact(lineupSide, matching, s.provider_player_id)

    return {
      provider_player_id: s.provider_player_id,
      name: s.short_name || s.player_name,
      role,
      status,
      status_note: statusNote,
      sot_per_90: sot,
      shots_per_90: shots,
      team_sot_share_pct: sharePct,
      shooting_impact: prof?.shooting_impact_score ?? null,
      defensive_impact: defImp,
      reliability: prof?.reliability_score ?? null,
      tactical_line_index: tacticalLineIndexForPlayer(lines, s.provider_player_id),
      sort_impact: Math.max(prof?.shooting_impact_score ?? 0, (defImp ?? 0) * 100),
    }
  })

  rows.sort((a, b) => {
    const ra = roleSortKey(a.role)
    const rb = roleSortKey(b.role)
    if (ra !== rb) return ra - rb
    if (a.tactical_line_index !== b.tactical_line_index) return a.tactical_line_index - b.tactical_line_index
    return b.sort_impact - a.sort_impact
  })

  return rows
}
