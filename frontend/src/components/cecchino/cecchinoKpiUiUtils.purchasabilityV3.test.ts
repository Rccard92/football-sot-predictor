import { describe, expect, it } from 'vitest'
import {
  formatPenaltyPointsNegative,
  purchasabilityV3BadgeClass,
  resolvePurchasabilityV3CellState,
} from './cecchinoKpiUiUtils'
import {
  AWAY_V3_ITEM,
  DERIVED_V3_ITEM,
  GATE_FAILED_V3_ITEM,
  MISSING_INPUTS_V3_ITEM,
  UNSUPPORTED_V3_ITEM,
} from './fixtures/purchasabilityV3AwayRegression'

describe('resolvePurchasabilityV3CellState', () => {
  it('snapshot assente → V3 non disponibile', () => {
    const s = resolvePurchasabilityV3CellState(undefined, { snapshotAvailable: false })
    expect(s.kind).toBe('snapshot_absent')
    expect(s.primary).toBe('—')
    expect(s.subtitle).toBe('V3 non disponibile')
    expect(s.analyzable).toBe(false)
  })

  it('gate fallito → Non attivato senza score 0', () => {
    const s = resolvePurchasabilityV3CellState(GATE_FAILED_V3_ITEM, {
      snapshotAvailable: true,
    })
    expect(s.kind).toBe('gate_failed')
    expect(s.primary).toBe('Non attivato')
    expect(s.subtitle).toBe('Nessun valore positivo')
    expect(s.score).toBeNull()
    expect(s.primary).not.toBe('0')
    expect(s.analyzable).toBe(true)
  })

  it('input mancanti → Non calcolabile', () => {
    const s = resolvePurchasabilityV3CellState(MISSING_INPUTS_V3_ITEM, {
      snapshotAvailable: true,
    })
    expect(s.kind).toBe('missing_inputs')
    expect(s.primary).toBe('Non calcolabile')
    expect(s.analyzable).toBe(true)
  })

  it('mercato non supportato', () => {
    const s = resolvePurchasabilityV3CellState(UNSUPPORTED_V3_ITEM, {
      snapshotAvailable: true,
    })
    expect(s.kind).toBe('unsupported')
    expect(s.primary).toBe('—')
    expect(s.subtitle).toBe('Non supportato')
    expect(s.analyzable).toBe(false)
  })

  it('score disponibile con chip candidato e Non validato', () => {
    const s = resolvePurchasabilityV3CellState(AWAY_V3_ITEM, { snapshotAvailable: true })
    expect(s.kind).toBe('score')
    expect(s.score).toBe(47)
    expect(s.showCandidateChip).toBe(true)
    expect(s.subtitle).toBe('Non validato')
  })

  it('quota derivata', () => {
    const s = resolvePurchasabilityV3CellState(DERIVED_V3_ITEM, { snapshotAvailable: true })
    expect(s.derivedQuote).toBe(true)
    expect(s.subtitle).toBe('Quota derivata · Solo diagnostico')
  })
})

describe('purchasabilityV3BadgeClass / formatPenaltyPointsNegative', () => {
  it('badge per classi score', () => {
    expect(purchasabilityV3BadgeClass('Media')).toContain('amber')
    expect(purchasabilityV3BadgeClass('Molto Alta')).toContain('emerald')
  })

  it('penalità con segno negativo', () => {
    expect(formatPenaltyPointsNegative(35)).toMatch(/^−/)
    expect(formatPenaltyPointsNegative(12.284)).toContain('12')
    expect(formatPenaltyPointsNegative(0)).not.toMatch(/^−/)
  })
})
