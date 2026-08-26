/** @vitest-environment jsdom */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const FORBIDDEN_IMPORT_SNIPPETS = [
  'downloadDailyPurchasabilityV35Audit',
  'triggerDailyPurchasabilityV35AuditDownload',
  'downloadPurchasabilityV35AnalysisExport',
  'triggerPurchasabilityV35AnalysisDownload',
  'V35_LIVE_EXPERIMENT_V1',
  'CecchinoPurchasabilityV35Panel',
  'indexPurchasabilityV35ByMarketKey',
]

describe('production route source — no V35 wiring', () => {
  it('CecchinoTodayPage non importa helper V35', () => {
    const src = readFileSync(
      resolve(__dirname, '../../pages/CecchinoTodayPage.tsx'),
      'utf8',
    )
    for (const s of FORBIDDEN_IMPORT_SNIPPETS) {
      expect(src).not.toContain(s)
    }
  })

  it('CecchinoTodayDetailPanel non importa pannello V35', () => {
    const src = readFileSync(resolve(__dirname, './CecchinoTodayDetailPanel.tsx'), 'utf8')
    expect(src).not.toContain('CecchinoPurchasabilityV35Panel')
    expect(src).not.toContain('indexPurchasabilityV35ByMarketKey')
    expect(src).toContain('CecchinoPurchasabilityV36Panel')
  })

  it('CecchinoTodayPageHeader non espone props V35', () => {
    const src = readFileSync(resolve(__dirname, './CecchinoTodayPageHeader.tsx'), 'utf8')
    expect(src).not.toContain('onDownloadDailyV35Audit')
    expect(src).not.toContain('onDownloadV35Analysis')
    expect(src).not.toContain('Scarica audit V3.5')
    expect(src).not.toContain('Scarica dataset V3.5')
  })

  it('V36 utils non dipendono da V35UiUtils', () => {
    const src = readFileSync(
      resolve(__dirname, './cecchinoPurchasabilityV36UiUtils.ts'),
      'utf8',
    )
    expect(src).not.toContain('cecchinoPurchasabilityV35UiUtils')
    expect(src).toContain('cecchinoPurchasabilityMarketKeys')
  })
})
