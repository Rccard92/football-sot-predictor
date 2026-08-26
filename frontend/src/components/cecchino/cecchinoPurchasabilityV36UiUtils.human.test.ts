import { describe, expect, it } from 'vitest'
import { HOME_V36_ITEM } from './fixtures/purchasabilityV36Fixtures'
import {
  buildV36HumanExplanation,
  v36BadgeClass,
} from './cecchinoPurchasabilityV36UiUtils'
import { scoreSemaphorePalette } from './PurchasabilityScoreRing'

describe('V3.6 human explanation + ring palette', () => {
  it('buildV36HumanExplanation is deterministic and avoids outcome language', () => {
    const e = buildV36HumanExplanation(HOME_V36_ITEM)
    expect(e.valore).toBeTruthy()
    expect(e.affidabilita).toBeTruthy()
    expect(e.struttura).toBeTruthy()
    expect(e.qualita).toBeTruthy()
    expect(e.conclusione).toMatch(/Punteggio/)
    const blob = `${e.valore} ${e.affidabilita} ${e.struttura} ${e.qualita} ${e.conclusione}`.toLowerCase()
    expect(blob).not.toMatch(/probabilit[aà] di vincere/)
    expect(blob).not.toMatch(/scommessa sicura/)
    expect(blob).not.toMatch(/alta probabilit/)
    expect(e.conclusione).toMatch(/non una previsione/)
  })

  it('v36BadgeClass uses persisted class label only', () => {
    expect(v36BadgeClass('Media')).toContain('amber')
    expect(v36BadgeClass('Molto Bassa')).toContain('red')
  })

  it('scoreSemaphorePalette progresses red→green by score bands', () => {
    expect(scoreSemaphorePalette(20).stroke).toBe('#dc2626')
    expect(scoreSemaphorePalette(45).stroke).toBe('#ea580c')
    expect(scoreSemaphorePalette(55).stroke).toBe('#ca8a04')
    expect(scoreSemaphorePalette(65).stroke).toBe('#65a30d')
    expect(scoreSemaphorePalette(85).stroke).toBe('#16a34a')
  })
})
