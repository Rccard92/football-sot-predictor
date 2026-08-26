/** @vitest-environment node */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('C1.3 V36 evaluation bundle — fixed date range', () => {
  it('page chiama sempre 2026-08-26..2026-08-30 senza selectedDay', () => {
    const page = readFileSync(
      resolve(__dirname, '../../pages/CecchinoTodayPage.tsx'),
      'utf8',
    )
    expect(page).toContain('V36_EVALUATION_BUNDLE_DATE_FROM')
    expect(page).toContain('V36_EVALUATION_BUNDLE_DATE_TO')
    expect(page).toContain('downloadV36EvaluationBundle')
    expect(page).toContain('handleDownloadV36EvaluationBundle')
    // Non deve passare selectedDay al download bundle
    const handlerStart = page.indexOf('handleDownloadV36EvaluationBundle')
    const handlerSlice = page.slice(handlerStart, handlerStart + 800)
    expect(handlerSlice).toContain('V36_EVALUATION_BUNDLE_DATE_FROM')
    expect(handlerSlice).toContain('V36_EVALUATION_BUNDLE_DATE_TO')
    expect(handlerSlice).not.toContain('selectedDay')
  })

  it('API helper punta all endpoint evaluation-bundle e filename corretto', () => {
    const api = readFileSync(resolve(__dirname, '../../lib/cecchinoTodayApi.ts'), 'utf8')
    expect(api).toContain("V36_EVALUATION_BUNDLE_DATE_FROM = '2026-08-26'")
    expect(api).toContain("V36_EVALUATION_BUNDLE_DATE_TO = '2026-08-30'")
    expect(api).toContain('purchasability-v36-evaluation-bundle')
    expect(api).toContain('cecchino-v36-analysis-${dateFrom}_${dateTo}.zip')
  })
})
