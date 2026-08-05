import { describe, expect, it } from 'vitest'
import {
  purchasabilityV31BadgeClass,
  resolvePurchasabilityV31CellState,
} from './cecchinoKpiUiUtils'
import {
  AWAY_V31_ITEM,
  GATE_FAILED_RATING_V31_ITEM,
  GATE_FAILED_NO_VALUE_V31_ITEM,
  NON_CALCULABLE_MISSING_QUOTE_V31_ITEM,
  NON_CALCULABLE_DERIVED_V31_ITEM,
  NON_CALCULABLE_INSUFFICIENT_HISTORY_V31_ITEM,
} from './fixtures/purchasabilityV31Fixtures'

describe('resolvePurchasabilityV31CellState', () => {
  it('snapshot assente → "—" senza subtitle', () => {
    const s = resolvePurchasabilityV31CellState(undefined, { snapshotAvailable: false })
    expect(s.kind).toBe('snapshot_absent')
    expect(s.primary).toBe('—')
    expect(s.subtitle).toBeNull()
    expect(s.analyzable).toBe(false)
  })

  it('loading → "Calcolo in corso…"', () => {
    const s = resolvePurchasabilityV31CellState(undefined, {
      snapshotAvailable: true,
      loading: true,
    })
    expect(s.kind).toBe('loading')
    expect(s.primary).toBe('Calcolo in corso…')
    expect(s.analyzable).toBe(false)
  })

  it('score calcolato → mostra score con badge', () => {
    const s = resolvePurchasabilityV31CellState(AWAY_V31_ITEM, {
      snapshotAvailable: true,
    })
    expect(s.kind).toBe('score')
    expect(s.score).toBe(52)
    expect(s.classLabel).toBe('Media')
    expect(s.showScoreBadge).toBe(true)
    expect(s.analyzable).toBe(true)
  })

  it('gate fallito per rating → "Non attivato" + "Rating sotto 50"', () => {
    const s = resolvePurchasabilityV31CellState(GATE_FAILED_RATING_V31_ITEM, {
      snapshotAvailable: true,
    })
    expect(s.kind).toBe('gate_failed')
    expect(s.primary).toBe('Non attivato')
    expect(s.subtitle).toBe('Rating sotto 50')
    expect(s.score).toBeNull()
    expect(s.analyzable).toBe(true)
  })

  it('gate fallito per nessun valore → "Non attivato" + "Nessun valore positivo"', () => {
    const s = resolvePurchasabilityV31CellState(GATE_FAILED_NO_VALUE_V31_ITEM, {
      snapshotAvailable: true,
    })
    expect(s.kind).toBe('gate_failed')
    expect(s.primary).toBe('Non attivato')
    expect(s.subtitle).toBe('Nessun valore positivo')
    expect(s.analyzable).toBe(true)
  })

  it('non calcolabile per quota mancante → "Non calcolabile" + "Quota mancante"', () => {
    const s = resolvePurchasabilityV31CellState(NON_CALCULABLE_MISSING_QUOTE_V31_ITEM, {
      snapshotAvailable: true,
    })
    expect(s.kind).toBe('non_calculable')
    expect(s.primary).toBe('Non calcolabile')
    expect(s.subtitle).toBe('Quota mancante')
    expect(s.analyzable).toBe(true)
  })

  it('non calcolabile per quota derivata → "Non calcolabile" + "Quota derivata"', () => {
    const s = resolvePurchasabilityV31CellState(NON_CALCULABLE_DERIVED_V31_ITEM, {
      snapshotAvailable: true,
    })
    expect(s.kind).toBe('non_calculable')
    expect(s.primary).toBe('Non calcolabile')
    expect(s.subtitle).toBe('Quota derivata')
    expect(s.analyzable).toBe(true)
  })

  it('non calcolabile per storico insufficiente → "Non calcolabile" + "Storico insufficiente"', () => {
    const s = resolvePurchasabilityV31CellState(NON_CALCULABLE_INSUFFICIENT_HISTORY_V31_ITEM, {
      snapshotAvailable: true,
    })
    expect(s.kind).toBe('non_calculable')
    expect(s.primary).toBe('Non calcolabile')
    expect(s.subtitle).toBe('Storico insufficiente')
    expect(s.analyzable).toBe(true)
  })

  it('item null con snapshot disponibile → snapshot_absent', () => {
    const s = resolvePurchasabilityV31CellState(null, { snapshotAvailable: true })
    expect(s.kind).toBe('snapshot_absent')
    expect(s.primary).toBe('—')
  })

  it('loading ha priorità su snapshot assente', () => {
    const s = resolvePurchasabilityV31CellState(undefined, {
      snapshotAvailable: false,
      loading: true,
    })
    expect(s.kind).toBe('loading')
    expect(s.primary).toBe('Calcolo in corso…')
  })

  it('tutti gli stati gate_failed e non_calculable sono analyzable', () => {
    expect(
      resolvePurchasabilityV31CellState(GATE_FAILED_RATING_V31_ITEM, {
        snapshotAvailable: true,
      }).analyzable,
    ).toBe(true)
    expect(
      resolvePurchasabilityV31CellState(GATE_FAILED_NO_VALUE_V31_ITEM, {
        snapshotAvailable: true,
      }).analyzable,
    ).toBe(true)
    expect(
      resolvePurchasabilityV31CellState(NON_CALCULABLE_MISSING_QUOTE_V31_ITEM, {
        snapshotAvailable: true,
      }).analyzable,
    ).toBe(true)
  })
})

describe('purchasabilityV31BadgeClass', () => {
  it('restituisce classi corrette per ogni classe score', () => {
    expect(purchasabilityV31BadgeClass('Molto Bassa')).toContain('slate')
    expect(purchasabilityV31BadgeClass('Bassa')).toContain('orange')
    expect(purchasabilityV31BadgeClass('Media')).toContain('amber')
    expect(purchasabilityV31BadgeClass('Alta')).toContain('sky')
    expect(purchasabilityV31BadgeClass('Molto Alta')).toContain('emerald')
    expect(purchasabilityV31BadgeClass(null)).toContain('slate')
  })
})
