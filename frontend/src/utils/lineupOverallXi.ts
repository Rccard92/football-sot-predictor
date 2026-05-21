import type { LineupImpactSideSimulation } from '../types/lineupImpact'
import type { SportApiPlayerMatchRow } from '../types/lineupImpact'
import type { PlayerDbProfileRow } from '../types/playerDbProfiles'
import type { SportApiLineupPlayer } from '../types/sportapi'
import { sortStartersByOriginalIndex } from './sportapiFormation'

export type ConfidenceLevel = 'alta' | 'media' | 'bassa' | 'molto_bassa'

export type OverallXiBreakdown = {
  overall: number | null
  attacking_sot_score: number | null
  team_base_strength_score: number | null
  lineup_attacking_power_score: number | null
  top_players_presence_score: number | null
  defensive_stability_score: number | null
  xi_continuity_score: number | null
  availability_score: number | null
  confidence_score: number | null
  confidence_level: ConfidenceLevel
  partial: boolean
  partial_note?: string
  explanation_bullets: string[]
}

const LEAGUE_SOT_MIN = 2.8
const LEAGUE_SOT_MAX = 6.2

function clamp0_100(v: number): number {
  return Math.max(0, Math.min(100, Math.round(v)))
}

function avg(nums: number[]): number | null {
  if (!nums.length) return null
  return nums.reduce((a, b) => a + b, 0) / nums.length
}

export function confidenceLabelFromScore(score: number): ConfidenceLevel {
  if (score >= 85) return 'alta'
  if (score >= 65) return 'media'
  if (score >= 40) return 'bassa'
  return 'molto_bassa'
}

export function confidenceLabelDisplay(level: ConfidenceLevel): string {
  const map: Record<ConfidenceLevel, string> = {
    alta: 'Alta',
    media: 'Media',
    bassa: 'Bassa',
    molto_bassa: 'Molto bassa',
  }
  return map[level]
}

export function teamBaseAttackScoreFromV11(teamBaseSotV11: number | null | undefined): number | null {
  if (teamBaseSotV11 == null || Number.isNaN(teamBaseSotV11)) return null
  return clamp0_100(((teamBaseSotV11 - LEAGUE_SOT_MIN) / (LEAGUE_SOT_MAX - LEAGUE_SOT_MIN)) * 100)
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

function countUnmappedStarters(
  starters: SportApiLineupPlayer[],
  matching: SportApiPlayerMatchRow[] | undefined,
): number {
  let n = 0
  for (const s of starters) {
    const m = matchBySportApiId(matching, s.provider_player_id)
    if (!m || m.recommendation !== 'AUTO_SAFE') n += 1
  }
  return n
}

export function computeStartersSotPowerScore(
  starters: SportApiLineupPlayer[],
  lineupSide: LineupImpactSideSimulation | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
  profilesByApiId: Map<number, PlayerDbProfileRow>,
  teamBaseSotV11: number | null | undefined,
): number | null {
  const perPlayer: number[] = []
  const sot90s: number[] = []

  for (const s of starters) {
    const top = lineupSide?.top_sot_players?.find((p) => p.sportapi_player_id === s.provider_player_id)
    const prof = profileForStarter(s, matching, profilesByApiId)
    const sot =
      top?.sot_per_90 ??
      (prof?.shots_on_per90 != null ? Number(prof.shots_on_per90) : null)
    if (sot == null || Number.isNaN(sot)) continue
    sot90s.push(sot)
    const share =
      top?.team_sot_share ??
      (prof?.team_sot_share != null ? Number(prof.team_sot_share) / 100 : 0)
    perPlayer.push(sot * 40 + share * 60)
  }

  if (!sot90s.length) return null

  const maxSot = Math.max(...sot90s)
  const teamPerPlayer = teamBaseSotV11 != null ? teamBaseSotV11 / 11 : 0.35
  const normalized = sot90s.map((sot) => {
    const vsMax = maxSot > 0 ? (sot / maxSot) * 55 : 0
    const vsTeam = teamPerPlayer > 0 ? Math.min(45, (sot / (teamPerPlayer * 3)) * 45) : 0
    return vsMax + vsTeam
  })

  return clamp0_100(avg(normalized) ?? avg(perPlayer) ?? 50)
}

export function computeTopPlayersPresenceScore(
  lineupSide: LineupImpactSideSimulation | undefined,
): number | null {
  const top5 = lineupSide?.top_sot_players ?? lineupSide?.top5_sot_players ?? []
  if (!top5.length) return null

  let score = 55
  const present = lineupSide?.top5_present ?? top5.filter((p) => p.status === 'STARTER')
  const missing = lineupSide?.top5_missing ?? top5.filter((p) => p.status === 'MISSING' || p.status === 'OUT_OF_LINEUP')

  const presentShare = present.reduce((a, p) => a + (p.team_sot_share ?? 0), 0)
  const missingShare = missing.reduce((a, p) => a + (p.team_sot_share ?? 0), 0)
  score = clamp0_100(50 + presentShare * 120 - missingShare * 80)

  const credit = lineupSide?.replacement_credit_share ?? 0
  if (credit > 0) score = clamp0_100(score + Math.min(12, credit * 80))

  const benchTop = top5.filter((p) => p.status === 'BENCH')
  if (benchTop.length) score = clamp0_100(score - benchTop.length * 4)

  return score
}

export function computeReplacementAdjustmentScore(lineupSide: LineupImpactSideSimulation | undefined): number {
  const credit = lineupSide?.replacement_credit_share ?? 0
  const netLoss = lineupSide?.net_lineup_loss_share ?? lineupSide?.net_missing_sot_share ?? 0
  let score = 50
  if (credit > 0) score = clamp0_100(50 + Math.min(35, credit * 120))
  if (netLoss > 0) score = clamp0_100(score - Math.min(25, netLoss * 90))
  return score
}

export function computeAttackingSotScore(
  starters: SportApiLineupPlayer[],
  lineupSide: LineupImpactSideSimulation | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
  profilesByApiId: Map<number, PlayerDbProfileRow>,
  teamBaseSotV11: number | null | undefined,
): number | null {
  const teamBase = teamBaseAttackScoreFromV11(teamBaseSotV11)
  const startersPower = computeStartersSotPowerScore(
    starters,
    lineupSide,
    matching,
    profilesByApiId,
    teamBaseSotV11,
  )
  const topPresence = computeTopPlayersPresenceScore(lineupSide)
  const replacement = computeReplacementAdjustmentScore(lineupSide)

  const parts: { v: number | null; w: number }[] = [
    { v: teamBase, w: 0.35 },
    { v: startersPower, w: 0.35 },
    { v: topPresence, w: 0.2 },
    { v: replacement, w: 0.1 },
  ]

  if (!parts.some((p) => p.v != null)) return null

  let sum = 0
  let wSum = 0
  for (const p of parts) {
    const val = p.v ?? 50
    sum += val * p.w
    wSum += p.w
  }
  let score = clamp0_100(wSum > 0 ? sum / wSum : sum)

  if (teamBaseSotV11 != null && teamBaseSotV11 >= 4.8 && (topPresence ?? 0) >= 50) {
    score = Math.max(score, 58)
  }

  return score
}

export function computeDefensiveStabilityScore(
  starters: SportApiLineupPlayer[],
  lineupSide: LineupImpactSideSimulation | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
): number | null {
  const starterPlayerIds = new Set<number>()
  for (const s of starters) {
    const m = matchBySportApiId(matching, s.provider_player_id)
    if (m?.player_id != null) starterPlayerIds.add(Number(m.player_id))
  }

  const imps: number[] = []
  for (const d of lineupSide?.defensive_key_players ?? []) {
    if (d.player_id != null && starterPlayerIds.has(Number(d.player_id)) && d.defensive_importance != null) {
      imps.push(d.defensive_importance)
    }
  }

  let score = imps.length ? clamp0_100(avg(imps)! * 92 + 8) : 48

  const hasGk = starters.some((s) => (s.display_role || '') === 'P')
  if (hasGk) score = clamp0_100(score + 6)

  const defMissing = (lineupSide?.defensive_key_players ?? []).filter(
    (d) => d.status === 'MISSING' || d.status === 'OUT_OF_LINEUP',
  )
  score = clamp0_100(score - defMissing.length * 9)

  const netDefLoss = lineupSide?.net_defensive_loss
  if (netDefLoss != null && netDefLoss > 0) {
    score = clamp0_100(score - Math.min(28, netDefLoss * 110))
  }

  const weak = lineupSide?.defensive_weakness_factor
  if (weak != null && weak > 1) {
    score = clamp0_100(score - Math.min(22, (weak - 1) * 45))
  }

  return imps.length || hasGk || weak != null || defMissing.length ? score : null
}

export function computeXiContinuityScore(
  starters: SportApiLineupPlayer[],
  matching: SportApiPlayerMatchRow[] | undefined,
  profilesByApiId: Map<number, PlayerDbProfileRow>,
): number | null {
  const minutes: number[] = []
  let unmapped = 0
  let lowReliability = 0

  for (const s of starters) {
    const m = matchBySportApiId(matching, s.provider_player_id)
    const prof = profileForStarter(s, matching, profilesByApiId)
    if (!m || m.recommendation !== 'AUTO_SAFE') unmapped += 1
    const mins = prof?.minutes_total ?? prof?.recent_minutes_last5
    if (mins != null && mins > 0) minutes.push(mins)
    if (prof?.reliability_score != null && prof.reliability_score < 40) lowReliability += 1
  }

  if (!minutes.length && unmapped === starters.length) return null

  let score = 58
  const meanMin = avg(minutes)
  if (meanMin != null) {
    score = clamp0_100(35 + Math.min(55, (meanMin / 2500) * 55))
  }

  score = clamp0_100(score - unmapped * 7 - lowReliability * 5)

  const mp = avg(
    starters
      .map((s) => profileForStarter(s, matching, profilesByApiId)?.matches_played)
      .filter((x): x is number => x != null && x > 0),
  )
  if (mp != null) score = clamp0_100(score * 0.7 + Math.min(100, (mp / 30) * 100) * 0.3)

  return score
}

export function computeAvailabilityScore(
  starters: SportApiLineupPlayer[],
  matching: SportApiPlayerMatchRow[] | undefined,
  lineupSide: LineupImpactSideSimulation | undefined,
  missingCount: number,
): number | null {
  if (!starters.length) return null

  let score = 72
  if (starters.length === 11) score += 12
  else score -= (11 - starters.length) * 9

  let unmapped = 0
  let outOfLineup = 0
  for (const s of starters) {
    const m = matchBySportApiId(matching, s.provider_player_id)
    if (!m || m.recommendation !== 'AUTO_SAFE') unmapped += 1
    const top = lineupSide?.top_sot_players?.find((p) => p.sportapi_player_id === s.provider_player_id)
    if (top?.status === 'OUT_OF_LINEUP' || top?.status === 'UNMAPPED') outOfLineup += 1
  }

  score = clamp0_100(score - unmapped * 5 - outOfLineup * 4 - Math.min(20, missingCount * 3))

  const missingTop5 = lineupSide?.top5_missing?.length ?? 0
  score = clamp0_100(score - missingTop5 * 6)

  return score
}

export function computeConfidenceScore(
  starters: SportApiLineupPlayer[],
  matching: SportApiPlayerMatchRow[] | undefined,
  opts: {
    confirmed?: boolean | null
    confidenceScore?: number | null
    fetchedAt?: string | null
    profilesMissing?: boolean
    rosterSyncHint?: string
  },
): { score: number | null; level: ConfidenceLevel } {
  if (!starters.length) return { score: null, level: 'bassa' }

  let score = 25
  if (opts.confirmed === true) score += 28
  else if (opts.confirmed === false) score += 12

  const confs: number[] = []
  let unmapped = 0
  for (const s of starters) {
    const m = matchBySportApiId(matching, s.provider_player_id)
    if (m?.confidence_score != null) confs.push(m.confidence_score * 100)
    if (!m || m.recommendation !== 'AUTO_SAFE') unmapped += 1
  }
  const meanConf = avg(confs)
  if (meanConf != null) score += meanConf * 0.25
  score -= unmapped * 5
  if (unmapped >= 4) score -= 15

  if (opts.rosterSyncHint === 'ok') score += 12
  else if (opts.rosterSyncHint === 'stale' || opts.rosterSyncHint === 'missing') score -= 12

  if (!opts.profilesMissing) score += 10
  else score -= 18

  if (opts.fetchedAt) {
    try {
      const ageH = (Date.now() - new Date(opts.fetchedAt).getTime()) / 3600000
      if (ageH > 72) score -= 15
      else if (ageH > 48) score -= 8
      else if (ageH < 24) score += 6
    } catch {
      /* ignore */
    }
  }

  if (opts.confidenceScore != null) {
    score = score * 0.6 + clamp0_100(opts.confidenceScore * 100) * 0.4
  }

  const final = clamp0_100(score)
  return { score: final, level: confidenceLabelFromScore(final) }
}

function buildOverallExplanationBullets(
  lineupSide: LineupImpactSideSimulation | undefined,
  scores: {
    attacking: number | null
    teamBase: number | null
    topPresence: number | null
    defensive: number | null
    confidence: number | null
    confidenceLevel: ConfidenceLevel
    confirmed?: boolean | null
    unmappedCount: number
    mappedOffensiveStarters: number
  },
): string[] {
  const bullets: string[] = []

  if ((scores.attacking ?? 0) >= 60 && (scores.teamBase ?? 0) >= 55) {
    bullets.push(
      `Attacco SOT sostenuto da una base squadra alta e da ${scores.mappedOffensiveStarters} titolari offensivi mappati.`,
    )
  } else if ((scores.attacking ?? 0) < 45 && (scores.teamBase ?? 0) >= 55) {
    bullets.push(
      'Attacco SOT dei titolari sotto la forza base squadra: verificare assenze o mapping incompleto.',
    )
  }

  if (scores.confidenceLevel === 'bassa' || scores.confidenceLevel === 'molto_bassa') {
    const parts: string[] = []
    if (scores.confirmed === false) parts.push('formazione probabile')
    if (scores.unmappedCount >= 3) parts.push('alcuni giocatori non mappati')
    if (parts.length) {
      bullets.push(`Confidence ridotta: ${parts.join(' e ')}.`)
    }
  }

  if ((scores.defensive ?? 0) >= 70) {
    bullets.push('Solidità difensiva alta: portiere e linea difensiva principale presenti.')
  } else if ((scores.topPresence ?? 0) < 45) {
    bullets.push('Presenza top shooter ridotta: assenze o giocatori fuori XI incidono sul punteggio.')
  }

  const fromLi = pickExplanationBullets(lineupSide)
  if (fromLi.length && bullets.length < 3) {
    bullets.push(fromLi[0])
  }

  return bullets.slice(0, 3)
}

function pickExplanationBullets(lineupSide: LineupImpactSideSimulation | undefined): string[] {
  const pool: string[] = []
  for (const r of lineupSide?.offensive_reasons ?? []) {
    if (r && !pool.includes(r)) pool.push(r)
  }
  for (const r of lineupSide?.defensive_reasons ?? []) {
    if (r && !pool.includes(r)) pool.push(r)
  }
  for (const r of lineupSide?.reasons ?? []) {
    if (r && !pool.includes(r)) pool.push(r)
  }

  if (lineupSide?.roster_sync_hint === 'ok') {
    pool.push('Rosa attuale aggiornata: giocatori trasferiti esclusi dal calcolo.')
  } else if (lineupSide?.roster_sync_hint === 'stale' || lineupSide?.roster_sync_hint === 'missing') {
    pool.push('Rosa attuale non sincronizzata: verificare sync squadre da Admin.')
  }

  return pool.slice(0, 3)
}

export function computeLineupOverallXi(
  starters: SportApiLineupPlayer[],
  _formation: string | null | undefined,
  lineupSide: LineupImpactSideSimulation | undefined,
  matching: SportApiPlayerMatchRow[] | undefined,
  profilesByApiId: Map<number, PlayerDbProfileRow>,
  meta: {
    confirmed?: boolean | null
    confidenceScore?: number | null
    fetchedAt?: string | null
    profilesMissing?: boolean
    rosterSyncHint?: string
    missingPlayersCount?: number
    teamBaseSotV11?: number | null
  },
): OverallXiBreakdown {
  const ordered = sortStartersByOriginalIndex(starters)
  const teamBaseSotV11 = meta.teamBaseSotV11 ?? lineupSide?.base_sot ?? lineupSide?.base_expected_sot ?? null

  const teamBaseStrength = teamBaseAttackScoreFromV11(teamBaseSotV11)
  const startersPower = computeStartersSotPowerScore(
    ordered,
    lineupSide,
    matching,
    profilesByApiId,
    teamBaseSotV11,
  )
  const attacking = computeAttackingSotScore(
    ordered,
    lineupSide,
    matching,
    profilesByApiId,
    teamBaseSotV11,
  )
  const lineupAttackingPower =
    attacking != null && startersPower != null
      ? clamp0_100(attacking * 0.55 + startersPower * 0.45)
      : attacking ?? startersPower

  const topPresence = computeTopPlayersPresenceScore(lineupSide)
  const defensive = computeDefensiveStabilityScore(ordered, lineupSide, matching)
  const continuity = computeXiContinuityScore(ordered, matching, profilesByApiId)
  const availability = computeAvailabilityScore(
    ordered,
    matching,
    lineupSide,
    meta.missingPlayersCount ?? 0,
  )

  const unmappedCount = countUnmappedStarters(ordered, matching)
  let mappedOffensive = 0
  for (const s of ordered) {
    const role = s.display_role || ''
    if (role !== 'A' && role !== 'C') continue
    const m = matchBySportApiId(matching, s.provider_player_id)
    if (m?.recommendation === 'AUTO_SAFE') mappedOffensive += 1
  }

  const { score: confidence, level: confidence_level } = computeConfidenceScore(ordered, matching, {
    confirmed: meta.confirmed,
    confidenceScore: meta.confidenceScore,
    fetchedAt: meta.fetchedAt,
    profilesMissing: meta.profilesMissing,
    rosterSyncHint: meta.rosterSyncHint ?? lineupSide?.roster_sync_hint,
  })

  const components = [
    { v: teamBaseStrength, w: 0.25 },
    { v: lineupAttackingPower, w: 0.25 },
    { v: defensive, w: 0.2 },
    { v: topPresence, w: 0.15 },
    { v: continuity, w: 0.1 },
    { v: availability, w: 0.05 },
  ]
  const defaults = [55, 52, 50, 50, 52, 60]
  const partial = components.some((c) => c.v == null)

  let overall: number | null = null
  if (components.some((c) => c.v != null)) {
    let sum = 0
    let wSum = 0
    components.forEach((c, i) => {
      const val = c.v ?? defaults[i]
      sum += val * c.w
      wSum += c.w
    })
    overall = clamp0_100(wSum > 0 ? sum / wSum : sum)
  }

  const rawOverall = overall

  if (teamBaseSotV11 != null && teamBaseSotV11 >= 4.8 && (topPresence ?? 0) >= 50 && overall != null) {
    overall = Math.max(overall, 68)
  }

  if (unmappedCount >= 4 && overall != null && rawOverall != null) {
    overall = Math.max(overall, rawOverall - 8)
  }

  let attackingFinal = attacking
  if (teamBaseSotV11 != null && teamBaseSotV11 >= 4.8 && (topPresence ?? 0) >= 50 && attackingFinal != null) {
    attackingFinal = Math.max(attackingFinal, 58)
  }

  return {
    overall,
    attacking_sot_score: attackingFinal,
    team_base_strength_score: teamBaseStrength,
    lineup_attacking_power_score: lineupAttackingPower,
    top_players_presence_score: topPresence,
    defensive_stability_score: defensive,
    xi_continuity_score: continuity,
    availability_score: availability,
    confidence_score: confidence,
    confidence_level,
    partial,
    partial_note: partial ? 'Alcuni componenti stimati con dati parziali.' : undefined,
    explanation_bullets: buildOverallExplanationBullets(lineupSide, {
      attacking: attackingFinal,
      teamBase: teamBaseStrength,
      topPresence,
      defensive,
      confidence,
      confidenceLevel: confidence_level,
      confirmed: meta.confirmed,
      unmappedCount,
      mappedOffensiveStarters: mappedOffensive,
    }),
  }
}

export function profilesToApiIdMap(players: PlayerDbProfileRow[] | undefined): Map<number, PlayerDbProfileRow> {
  const m = new Map<number, PlayerDbProfileRow>()
  for (const p of players ?? []) {
    if (p.api_player_id != null) m.set(Number(p.api_player_id), p)
  }
  return m
}

/** @deprecated use computeTopPlayersPresenceScore */
export function computeOffensivePresenceScore(lineupSide: LineupImpactSideSimulation | undefined): number | null {
  return computeTopPlayersPresenceScore(lineupSide)
}
