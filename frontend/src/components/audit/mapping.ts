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
  const drivers: MainDriver[] = []
  const active = data.active_model_version ?? null
  const fx = data.fixture
  const idx = idxVars(data)

  if (active === 'baseline_v1_0_sot') {
    const xgHome = pickTeamVar(idx, 'v10_component_expected_goals', fx.home_team.id)?.value ?? null
    const xgAway = pickTeamVar(idx, 'v10_component_expected_goals', fx.away_team.id)?.value ?? null
    drivers.push({
      id: 'v10_xg_component',
      title: `xG (expected_goals): ${fx.home_team.name} ${fmtNum(xgHome)} · ${fx.away_team.name} ${fmtNum(xgAway)}`,
      direction: 'info',
      impact: 'alto',
      explanation: '7° termine additivo v1.0: correzione da expected_goals su base esplicita v0.4.',
    })
    const baseHome =
      pickTeamVar(idx, 'v10_term_season_avg_sot_for', fx.home_team.id)?.value ??
      pickTeamVar(idx, 'v10_term_core_sot', fx.home_team.id)?.value ??
      null
    const baseAway =
      pickTeamVar(idx, 'v10_term_season_avg_sot_for', fx.away_team.id)?.value ??
      pickTeamVar(idx, 'v10_term_core_sot', fx.away_team.id)?.value ??
      null
    if (baseHome != null || baseAway != null) {
      drivers.push({
        id: 'v10_explicit_base',
        title: `Base esplicita: ${fx.home_team.name} ${fmtNum(baseHome)} · ${fx.away_team.name} ${fmtNum(baseAway)}`,
        direction: 'info',
        impact: 'medio',
        explanation: 'Termini espliciti v0.4 riportati nella formula v1.0 (senza ricalcolo).',
      })
    }
    return drivers
  }

  if (active === 'baseline_v0_4_offensive_core_sot') {
    const hv = pickTeamVar(idx, 'v04_component_offensive_production', fx.home_team.id)?.value ?? null
    const av = pickTeamVar(idx, 'v04_component_offensive_production', fx.away_team.id)?.value ?? null
    drivers.push({
      id: 'v04_offensive_component',
      title: `Produzione offensiva: ${fx.home_team.name} ${fmtNum(hv)} · ${fx.away_team.name} ${fmtNum(av)}`,
      direction: 'info',
      impact: 'alto',
      explanation: 'Componente applicata al calcolo v0.4 (scala SOT attesi, cap prudente).',
    })
    return drivers
  }

  if (active === 'baseline_v0_3_core_sot') {
    const keys: Array<{ k: string; title: string; w: DriverImpact }> = [
      { k: 'v03_component_core_sot', title: 'Core SOT diretto', w: 'alto' },
      { k: 'v03_component_shot_volume', title: 'Volume tiri', w: 'medio' },
      { k: 'v03_component_shot_accuracy', title: 'Precisione tiro', w: 'basso' },
      { k: 'v03_component_recent_form', title: 'Forma recente', w: 'basso' },
      { k: 'v03_component_goals_context', title: 'Goal context', w: 'basso' },
    ]
    for (const def of keys) {
      const hv = pickTeamVar(idx, def.k, fx.home_team.id)?.value ?? null
      const av = pickTeamVar(idx, def.k, fx.away_team.id)?.value ?? null
      drivers.push({
        id: `v03_${def.k}`,
        title: `${def.title}: ${fx.home_team.name} ${fmtNum(hv)} · ${fx.away_team.name} ${fmtNum(av)}`,
        direction: 'info',
        impact: def.w,
        explanation: 'Componente applicata al calcolo v0.3 (valori in scala SOT attesi).',
      })
    }
    return drivers
  }

  if (active === 'baseline_v0_2_player_adjusted') {
    const paHome = pickTeamVar(idx, 'player_adjustment', fx.home_team.id)?.value ?? null
    const paAway = pickTeamVar(idx, 'player_adjustment', fx.away_team.id)?.value ?? null
    if (paHome != null && paHome !== 0) {
      drivers.push({
        id: 'player_adj_home',
        title: `${fx.home_team.name}: player impact ${fmtSigned(paHome)}`,
        direction: paHome > 0 ? 'increase' : 'decrease',
        impact: Math.abs(paHome) >= 0.25 ? 'alto' : Math.abs(paHome) >= 0.1 ? 'medio' : 'basso',
        explanation: 'Correzione applicata nel modello v0.2 player adjusted.',
      })
    }
    if (paAway != null && paAway !== 0) {
      drivers.push({
        id: 'player_adj_away',
        title: `${fx.away_team.name}: player impact ${fmtSigned(paAway)}`,
        direction: paAway > 0 ? 'increase' : 'decrease',
        impact: Math.abs(paAway) >= 0.25 ? 'alto' : Math.abs(paAway) >= 0.1 ? 'medio' : 'basso',
        explanation: 'Correzione applicata nel modello v0.2 player adjusted.',
      })
    }
    return drivers
  }

  // baseline_v0_1: driver “tecnici” (solo informativi)
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

