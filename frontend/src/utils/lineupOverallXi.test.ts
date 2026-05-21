import { describe, expect, it } from 'vitest'
import type { PlayerDbProfileRow } from '../types/playerDbProfiles'
import type { SportApiLineupPlayer } from '../types/sportapi'
import {
  confidenceLabelFromScore,
  computeAttackingSotScore,
  computeConfidenceScore,
  computeLineupOverallXi,
  teamBaseAttackScoreFromV11,
} from './lineupOverallXi'

function mockProfile(apiId: number, sot90: number): PlayerDbProfileRow {
  return {
    player_id: String(apiId),
    api_player_id: apiId,
    name: `Player ${apiId}`,
    position: 'Attacker',
    team_sot_share: 10,
    shots_on_per90: sot90,
    shots_total_per90: sot90 * 2,
    shots_total: 100,
    shots_on: 50,
    shot_accuracy: 0.5,
    team_shots_share: 8,
    minutes_total: 2000,
    recent_minutes_last5: 400,
    matches_played: 28,
    avg_rating: 7,
    shooting_impact_score: 70,
    reliability_score: 80,
  }
}

describe('confidenceLabelFromScore', () => {
  it('maps score bands to labels', () => {
    expect(confidenceLabelFromScore(100)).toBe('alta')
    expect(confidenceLabelFromScore(85)).toBe('alta')
    expect(confidenceLabelFromScore(70)).toBe('media')
    expect(confidenceLabelFromScore(50)).toBe('bassa')
    expect(confidenceLabelFromScore(30)).toBe('molto_bassa')
  })
})

describe('computeConfidenceScore', () => {
  it('derives label from numeric score', () => {
    const starters = Array.from({ length: 11 }, (_, i) => ({
      provider_player_id: i + 1,
      player_name: `P${i}`,
      display_role: 'C',
    })) as SportApiLineupPlayer[]

    const matching = starters.map((s) => ({
      sportapi_player_id: s.provider_player_id,
      sportapi_player_name: s.player_name,
      confidence_score: 0.95,
      recommendation: 'AUTO_SAFE' as const,
      player_id: s.provider_player_id,
    }))

    const { score, level } = computeConfidenceScore(starters, matching, {
      confirmed: true,
      profilesMissing: false,
      fetchedAt: new Date().toISOString(),
      rosterSyncHint: 'ok',
    })

    expect(score).not.toBeNull()
    expect(score!).toBeGreaterThanOrEqual(85)
    expect(level).toBe('alta')
    expect(confidenceLabelFromScore(score!)).toBe(level)
  })
})

describe('Inter-like overall', () => {
  it('high base and starters yield realistic scores', () => {
    const starters = Array.from({ length: 11 }, (_, i) => ({
      provider_player_id: i + 100,
      player_name: `S${i}`,
      display_role: i < 4 ? 'A' : 'C',
      original_index: i,
    })) as SportApiLineupPlayer[]

    const matching = starters.map((s) => ({
      sportapi_player_id: s.provider_player_id,
      sportapi_player_name: s.player_name,
      confidence_score: 0.92,
      recommendation: 'AUTO_SAFE' as const,
      player_id: s.provider_player_id,
      api_sports_player_id: s.provider_player_id,
    }))

    const lineupSide = {
      team_name: 'Inter',
      base_sot: 5.2,
      top_sot_players: [
        { status: 'STARTER' as const, team_sot_share: 0.18, sot_per_90: 1.4, sportapi_player_id: 100 },
        { status: 'STARTER' as const, team_sot_share: 0.15, sot_per_90: 1.2, sportapi_player_id: 101 },
        { status: 'STARTER' as const, team_sot_share: 0.12, sot_per_90: 1.0, sportapi_player_id: 102 },
        { status: 'STARTER' as const, team_sot_share: 0.1, sot_per_90: 0.9, sportapi_player_id: 103 },
        { status: 'BENCH' as const, team_sot_share: 0.08, sot_per_90: 0.8, sportapi_player_id: 104 },
      ],
      replacement_credit_share: 0.05,
      net_lineup_loss_share: 0.02,
      roster_sync_hint: 'ok' as const,
    }

    const profilesMap = new Map(starters.map((s) => [s.provider_player_id, mockProfile(s.provider_player_id, 1.1)]))

    expect(teamBaseAttackScoreFromV11(5.2)).toBeGreaterThanOrEqual(65)

    const breakdown = computeLineupOverallXi(starters, '3-5-2', lineupSide, matching, profilesMap, {
      confirmed: true,
      teamBaseSotV11: 5.2,
      profilesMissing: false,
      fetchedAt: new Date().toISOString(),
    })

    expect(breakdown.attacking_sot_score!).toBeGreaterThanOrEqual(55)
    expect(breakdown.overall!).toBeGreaterThanOrEqual(68)
    expect(confidenceLabelFromScore(breakdown.confidence_score!)).toBe(breakdown.confidence_level)

    const attacking = computeAttackingSotScore(starters, lineupSide, matching, profilesMap, 5.2)
    expect(attacking!).toBeGreaterThanOrEqual(55)
  })
})
