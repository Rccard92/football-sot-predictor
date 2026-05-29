import type { LineupImpactSideSimulation, SportApiPlayerMatchRow } from '../types/lineupImpact'
import type { PlayerDbProfileRow } from '../types/playerDbProfiles'
import type { SportApiDisplayRole, SportApiLineupPlayer } from '../types/sportapi'
import {
  buildTacticalLayout,
  roleSortKey,
  sortStartersByOriginalIndex,
  tacticalLineIndexForLayout,
  tacticalRoleForPlayer,
} from './sportapiFormation'

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
  match_score: number | null
  match_status: string | null
  mapping_reason: string | null
  tactical_line_index: number
  original_index: number
  sort_impact: number
}

function matchRow(matching: SportApiPlayerMatchRow[] | undefined, providerId: number) {
  return matching?.find((m) => m.sportapi_player_id === providerId)
}

function isMappedMatch(m: SportApiPlayerMatchRow | undefined): boolean {
  if (!m?.api_sports_player_id) return false
  return m.recommendation === 'AUTO_SAFE' || m.recommendation === 'REVIEW'
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

function profileForStarter(
  s: SportApiLineupPlayer,
  matching: SportApiPlayerMatchRow[] | undefined,
  profilesByApiId: Map<number, PlayerDbProfileRow>,
): PlayerDbProfileRow | undefined {
  const m = matchRow(matching, s.provider_player_id)
  const apiId = m?.api_sports_player_id ?? m?.player_id
  if (apiId != null) {
    const byId = profilesByApiId.get(Number(apiId))
    if (byId) return byId
  }
  const name = (s.short_name || s.player_name || '').toLowerCase().trim()
  if (!name) return undefined
  for (const p of profilesByApiId.values()) {
    if (p.name.toLowerCase().includes(name) || name.includes(p.name.toLowerCase())) {
      return p
    }
  }
  return undefined
}

export function buildStarterFieldRows(
  formation: string | null | undefined,
  starters: SportApiLineupPlayer[],
  lineupSide: LineupImpactSideSimulation | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
  profilesByApiId: Map<number, PlayerDbProfileRow>,
): StarterFieldForceRow[] {
  const ordered = sortStartersByOriginalIndex(starters)
  const layout = buildTacticalLayout(formation, ordered)

  const rows: StarterFieldForceRow[] = ordered.map((s) => {
    const role = tacticalRoleForPlayer(layout, s.provider_player_id)
    const m = matchRow(matching, s.provider_player_id)
    const prof = profileForStarter(s, matching, profilesByApiId)
    const imp = impactForStarter(lineupSide, s.provider_player_id)

    let status = imp.status
    let statusNote = imp.status_note
    let mappingReason = m?.match_reason ?? m?.reason ?? null

    if (!isMappedMatch(m)) {
      status = 'UNMAPPED'
      statusNote = statusNote ?? mappingReason ?? 'Mapping profilo assente o sotto soglia'
    } else if (m?.recommendation === 'REVIEW') {
      statusNote = statusNote ?? 'Mapping da revisionare (score 75–89)'
    } else if (status === 'STARTER' && !imp.status_note) {
      statusNote = 'In formazione'
    }

    const sot =
      imp.sot_per_90 ??
      (m?.shots_on_per90 != null ? Number(m.shots_on_per90) : null) ??
      (prof?.shots_on_per90 != null ? Number(prof.shots_on_per90) : null)
    const shots =
      prof?.shots_total_per90 != null
        ? Number(prof.shots_total_per90)
        : prof?.shots_on_per90 != null
          ? Number(prof.shots_on_per90)
          : null
    const sharePct =
      imp.share_pct ??
      (m?.team_sot_share != null ? Math.round(m.team_sot_share * 1000) / 10 : null) ??
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
      shooting_impact:
        m?.shooting_impact_score ?? prof?.shooting_impact_score ?? null,
      defensive_impact: defImp,
      reliability: m?.reliability_score ?? prof?.reliability_score ?? null,
      match_score: m?.confidence_score ?? null,
      match_status: m?.recommendation ?? null,
      mapping_reason: mappingReason,
      tactical_line_index: tacticalLineIndexForLayout(layout, s.provider_player_id),
      original_index: s.original_index ?? 0,
      sort_impact: Math.max(prof?.shooting_impact_score ?? 0, (defImp ?? 0) * 100),
    }
  })

  rows.sort((a, b) => {
    if (a.tactical_line_index !== b.tactical_line_index) return a.tactical_line_index - b.tactical_line_index
    if (a.original_index !== b.original_index) return a.original_index - b.original_index
    return roleSortKey(a.role) - roleSortKey(b.role) || b.sort_impact - a.sort_impact
  })

  return rows
}
