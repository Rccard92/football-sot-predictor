import type { LineupImpactSideSimulation } from '../types/lineupImpact'
import type { SportApiPlayerMatchRow } from '../types/lineupImpact'
import type { PlayerDbProfileRow } from '../types/playerDbProfiles'
import type { SportApiLineupPlayer } from '../types/sportapi'
import { parseFormationCounts } from './sportapiFormation'

export type OverallXiBreakdown = {
  overall: number | null
  attacking_sot_score: number | null
  defensive_stability_score: number | null
  lineup_balance_score: number | null
  data_confidence_score: number | null
  partial: boolean
  partial_note?: string
}

function clamp0_100(v: number): number {
  return Math.max(0, Math.min(100, Math.round(v)))
}

function avg(nums: number[]): number | null {
  if (!nums.length) return null
  return nums.reduce((a, b) => a + b, 0) / nums.length
}

function matchBySportApiId(
  matching: SportApiPlayerMatchRow[] | undefined,
  providerId: number,
): SportApiPlayerMatchRow | undefined {
  return matching?.find((m) => m.sportapi_player_id === providerId)
}

function profileForStarter(
  starter: SportApiLineupPlayer,
  matching: SportApiPlayerMatchRow[] | undefined,
  profilesByApiId: Map<number, PlayerDbProfileRow>,
): PlayerDbProfileRow | undefined {
  const m = matchBySportApiId(matching, starter.provider_player_id)
  const apiId = m?.api_sports_player_id ?? m?.player_id
  if (apiId == null) return undefined
  return profilesByApiId.get(Number(apiId))
}

export function computeAttackingSotScore(
  starters: SportApiLineupPlayer[],
  lineupSide: LineupImpactSideSimulation | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
  profilesByApiId: Map<number, PlayerDbProfileRow>,
): number | null {
  const sot90s: number[] = []
  const shares: number[] = []

  for (const s of starters) {
    const top = lineupSide?.top_sot_players?.find((p) => p.sportapi_player_id === s.provider_player_id)
    const prof = profileForStarter(s, matching, profilesByApiId)
    const sot =
      top?.sot_per_90 ??
      (prof?.shots_on_per90 != null ? Number(prof.shots_on_per90) : null)
    if (sot != null && !Number.isNaN(sot)) sot90s.push(sot)
    const share = top?.team_sot_share ?? prof?.team_sot_share
    if (share != null && !Number.isNaN(share)) shares.push(share > 1 ? share / 100 : share)
  }

  let score = 50
  const meanSot = avg(sot90s)
  if (meanSot != null) score = clamp0_100((meanSot / 1.2) * 100)
  const meanShare = avg(shares)
  if (meanShare != null) score = clamp0_100(score * 0.6 + meanShare * 100 * 0.4)

  const startersPresent = lineupSide?.top5_present?.length ?? 0
  const startersMissing = lineupSide?.top5_missing?.length ?? 0
  if (startersPresent > 0) score = clamp0_100(score + Math.min(10, startersPresent * 2))
  if (startersMissing > 0) score = clamp0_100(score - Math.min(15, startersMissing * 5))

  const offFactor = lineupSide?.offensive_lineup_factor ?? lineupSide?.attacking_lineup_factor
  if (offFactor != null && offFactor > 0) {
    score = clamp0_100(score * 0.7 + Math.min(100, offFactor * 100) * 0.3)
  }

  return sot90s.length || shares.length || offFactor != null ? score : null
}

export function computeDefensiveStabilityScore(
  starters: SportApiLineupPlayer[],
  lineupSide: LineupImpactSideSimulation | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
): number | null {
  const defPlayers = lineupSide?.defensive_key_players ?? []
  const starterPlayerIds = new Set<number>()
  for (const s of starters) {
    const m = matchBySportApiId(matching, s.provider_player_id)
    if (m?.player_id != null) starterPlayerIds.add(Number(m.player_id))
  }

  const imps: number[] = []
  for (const d of defPlayers) {
    if (d.player_id != null && starterPlayerIds.has(Number(d.player_id))) {
      if (d.defensive_importance != null) imps.push(d.defensive_importance)
    }
  }

  let score = imps.length ? clamp0_100(avg(imps)! * 100) : 55

  const hasGk = starters.some((s) => s.display_role === 'P')
  if (hasGk) score = clamp0_100(score + 8)

  const netDefLoss = lineupSide?.net_defensive_loss
  if (netDefLoss != null && netDefLoss > 0) {
    score = clamp0_100(score - Math.min(25, netDefLoss * 100))
  }

  const weak = lineupSide?.defensive_weakness_factor ?? lineupSide?.opponent_defensive_weakness_factor
  if (weak != null && weak > 1) {
    score = clamp0_100(score - Math.min(20, (weak - 1) * 40))
  } else if (weak != null && weak < 1) {
    score = clamp0_100(score + Math.min(10, (1 - weak) * 30))
  }

  return imps.length || hasGk || weak != null ? score : null
}

export function computeLineupBalanceScore(
  starters: SportApiLineupPlayer[],
  formation: string | null | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
  tacticalRemainderSize: number,
): number | null {
  if (!starters.length) return null

  let score = 70
  if (starters.length === 11) score += 15
  else score -= (11 - starters.length) * 8

  const roles = new Set(starters.map((s) => s.display_role || 'C'))
  if (roles.has('P')) score += 5
  if (roles.has('D')) score += 5
  if (roles.has('C')) score += 5
  if (roles.has('A')) score += 5

  if (parseFormationCounts(formation).length) score += 5

  let unmapped = 0
  for (const s of starters) {
    const m = matchBySportApiId(matching, s.provider_player_id)
    if (!m || m.recommendation !== 'AUTO_SAFE' || !m.player_id) unmapped += 1
  }
  score -= unmapped * 6
  if (tacticalRemainderSize > 2) score -= 8

  return clamp0_100(score)
}

export function computeDataConfidenceScore(
  starters: SportApiLineupPlayer[],
  matching: SportApiPlayerMatchRow[] | undefined,
  opts: {
    confirmed?: boolean | null
    confidenceScore?: number | null
    fetchedAt?: string | null
    profilesMissing?: boolean
    rosterSyncHint?: string
  },
): number | null {
  if (!starters.length) return null

  let score = 20
  if (opts.confirmed === true) score += 40
  else if (opts.confirmed === false) score += 20

  const confs: number[] = []
  for (const s of starters) {
    const m = matchBySportApiId(matching, s.provider_player_id)
    if (m?.confidence_score != null) confs.push(m.confidence_score)
  }
  const meanConf = avg(confs)
  if (meanConf != null) score += clamp0_100(meanConf * 0.3)

  if (opts.rosterSyncHint === 'ok') score += 15
  else if (opts.rosterSyncHint === 'stale' || opts.rosterSyncHint === 'missing') score -= 10

  if (!opts.profilesMissing) score += 15
  else score -= 15

  if (opts.fetchedAt) {
    try {
      const ageH = (Date.now() - new Date(opts.fetchedAt).getTime()) / 3600000
      if (ageH > 48) score -= 10
      else if (ageH < 24) score += 5
    } catch {
      /* ignore */
    }
  }

  return clamp0_100(score)
}

export function computeLineupOverallXi(
  starters: SportApiLineupPlayer[],
  formation: string | null | undefined,
  lineupSide: LineupImpactSideSimulation | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
  profilesByApiId: Map<number, PlayerDbProfileRow>,
  meta: {
    confirmed?: boolean | null
    confidenceScore?: number | null
    fetchedAt?: string | null
    profilesMissing?: boolean
    rosterSyncHint?: string
    tacticalRemainderSize?: number
  },
): OverallXiBreakdown {
  const attacking = computeAttackingSotScore(starters, lineupSide, matching, profilesByApiId)
  const defensive = computeDefensiveStabilityScore(starters, lineupSide, matching)
  const balance = computeLineupBalanceScore(
    starters,
    formation,
    matching,
    meta.tacticalRemainderSize ?? 0,
  )
  const data = computeDataConfidenceScore(starters, matching, {
    confirmed: meta.confirmed,
    confidenceScore: meta.confidenceScore,
    fetchedAt: meta.fetchedAt,
    profilesMissing: meta.profilesMissing,
    rosterSyncHint: meta.rosterSyncHint ?? lineupSide?.roster_sync_hint,
  })

  const parts = [attacking, defensive, balance, data]
  const partial = parts.some((p) => p == null)
  const weights = [0.35, 0.25, 0.2, 0.2]
  const defaults = [50, 50, 50, 40]

  let overall: number | null = null
  if (parts.some((p) => p != null)) {
    let sum = 0
    for (let i = 0; i < 4; i++) {
      sum += (parts[i] ?? defaults[i]) * weights[i]
    }
    overall = clamp0_100(sum)
  }

  return {
    overall,
    attacking_sot_score: attacking,
    defensive_stability_score: defensive,
    lineup_balance_score: balance,
    data_confidence_score: data,
    partial,
    partial_note: partial ? 'Alcuni sotto-punteggi stimati con dati parziali.' : undefined,
  }
}

export function profilesToApiIdMap(players: PlayerDbProfileRow[] | undefined): Map<number, PlayerDbProfileRow> {
  const m = new Map<number, PlayerDbProfileRow>()
  for (const p of players ?? []) {
    if (p.api_player_id != null) m.set(Number(p.api_player_id), p)
  }
  return m
}
