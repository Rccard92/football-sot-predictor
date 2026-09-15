/** @vitest-environment node */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('C1.3 V36 evaluation bundle — fixed date range', () => {
  // il pulsante in Cecchino Today è stato tolto (decisione utente 15/09/2026): resta l'helper API
  it('API helper punta all endpoint evaluation-bundle e filename corretto', () => {
    const api = readFileSync(resolve(__dirname, '../../lib/cecchinoTodayApi.ts'), 'utf8')
    expect(api).toContain("V36_EVALUATION_BUNDLE_DATE_FROM = '2026-08-26'")
    expect(api).toContain("V36_EVALUATION_BUNDLE_DATE_TO = '2026-08-30'")
    expect(api).toContain('purchasability-v36-evaluation-bundle')
    expect(api).toContain('cecchino-v36-analysis-${dateFrom}_${dateTo}.zip')
  })
})
