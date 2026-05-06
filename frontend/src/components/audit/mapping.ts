import type { AuditResponse, AuditVariable } from './types'

export type FrameworkLevelId =
  | 'core'
  | 'player'
  | 'tactical'
  | 'motivation'
  | 'market'
  | 'referee'
  | 'sentiment'
  | 'technical'

export type Direction = 'increase' | 'decrease' | 'neutral' | 'info' | 'missing'

export type DriverImpact = 'alto' | 'medio' | 'basso'

export type MainDriver = {
  id: string
  title: string
  direction: Direction
  impact: DriverImpact
  explanation: string
}

export function idxVars(data: AuditResponse): Record<string, AuditVariable[]> {
  const out: Record<string, AuditVariable[]> = {}
  for (const s of data.sections) {
    for (const v of s.variables) {
      const k = v.key
      if (!out[k]) out[k] = []
      out[k].push(v)
    }
  }
  return out
}

export function pickTeamVar(
  index: Record<string, AuditVariable[]>,
  key: string,
  teamId: number,
): AuditVariable | null {
  const xs = index[key] ?? []
  return xs.find((v) => v.team_id === teamId) ?? null
}

export function fmtNum(n: number | null | undefined, maxFrac = 2): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toLocaleString('it-IT', { maximumFractionDigits: maxFrac })
}

export function fmtSigned(n: number | null | undefined, maxFrac = 2): string {
  if (n == null || Number.isNaN(n)) return '—'
  const s = n.toLocaleString('it-IT', { maximumFractionDigits: maxFrac })
  if (n > 0) return `+${s}`
  return s
}

export function buildMainDrivers(data: AuditResponse): MainDriver[] {
  const fx = data.fixture
  const idx = idxVars(data)

  const drivers: MainDriver[] = []

  const paHome = pickTeamVar(idx, 'player_adjustment', fx.home_team.id)
  const paAway = pickTeamVar(idx, 'player_adjustment', fx.away_team.id)
  const paHomeVal = paHome?.value ?? null
  const paAwayVal = paAway?.value ?? null

  if (paHomeVal != null && paHomeVal !== 0) {
    drivers.push({
      id: 'player_adj_home',
      title: `${fx.home_team.name}: player impact ${fmtSigned(paHomeVal)}`,
      direction: paHomeVal > 0 ? 'increase' : 'decrease',
      impact: Math.abs(paHomeVal) >= 0.25 ? 'alto' : Math.abs(paHomeVal) >= 0.1 ? 'medio' : 'basso',
      explanation:
        'Correzione v0.2 player adjusted basata sulla forza dei top shooter (rosa), non sulla formazione ufficiale.',
    })
  }
  if (paAwayVal != null && paAwayVal !== 0) {
    drivers.push({
      id: 'player_adj_away',
      title: `${fx.away_team.name}: player impact ${fmtSigned(paAwayVal)}`,
      direction: paAwayVal > 0 ? 'increase' : 'decrease',
      impact: Math.abs(paAwayVal) >= 0.25 ? 'alto' : Math.abs(paAwayVal) >= 0.1 ? 'medio' : 'basso',
      explanation:
        'Correzione v0.2 player adjusted basata sulla forza dei top shooter (rosa), non sulla formazione ufficiale.',
    })
  }

  const trendHome = pickTeamVar(idx, 'trend_last5_vs_season_sot_for', fx.home_team.id)?.notes ?? null
  if (trendHome && trendHome !== 'missing') {
    drivers.push({
      id: 'trend_home',
      title: `${fx.home_team.name}: forma SOT ultime 5 ${trendHome.replace('_', ' ')}`,
      direction: trendHome === 'sopra_media' ? 'increase' : trendHome === 'sotto_media' ? 'decrease' : 'neutral',
      impact: trendHome === 'sopra_media' || trendHome === 'sotto_media' ? 'medio' : 'basso',
      explanation: 'Confronto last5 vs media stagione (soglia ±5%).',
    })
  }

  const trendAway = pickTeamVar(idx, 'trend_last5_vs_season_sot_for', fx.away_team.id)?.notes ?? null
  if (trendAway && trendAway !== 'missing') {
    drivers.push({
      id: 'trend_away',
      title: `${fx.away_team.name}: forma SOT ultime 5 ${trendAway.replace('_', ' ')}`,
      direction: trendAway === 'sopra_media' ? 'increase' : trendAway === 'sotto_media' ? 'decrease' : 'neutral',
      impact: trendAway === 'sopra_media' || trendAway === 'sotto_media' ? 'medio' : 'basso',
      explanation: 'Confronto last5 vs media stagione (soglia ±5%).',
    })
  }

  // Nota trasparente: layer motivation non applicato in questo mercato audit
  drivers.push({
    id: 'motivation_info',
    title: 'Contesto/motivazione: non applicato (audit SOT)',
    direction: 'info',
    impact: 'basso',
    explanation: 'Il layer motivation/context è gestito come warning/roadmap e non entra nel calcolo SOT in questo step.',
  })

  return drivers
}

export const coreKeys = [
  'season_avg_sot_for',
  'season_avg_shots_for',
  'opponent_season_avg_sot_conceded',
  'season_avg_shots_conceded',
  'home_avg_sot_for',
  'away_avg_sot_for',
  'home_avg_sot_conceded',
  'away_avg_sot_conceded',
  'last5_avg_sot_for',
  'last5_avg_shots_for',
  'opponent_last5_avg_sot_conceded',
  'last5_avg_shots_conceded',
  'last10_avg_sot_for',
  'last10_avg_shots_for',
] as const

export const playerKeys = ['top5_players_by_impact', 'player_adjustment'] as const

