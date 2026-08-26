/** @vitest-environment jsdom */
import { describe, expect, it, afterEach, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CecchinoTodayDetailPanel } from './CecchinoTodayDetailPanel'
import type { CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { V35_VALID_SNAPSHOT } from './fixtures/purchasabilityV35Fixtures'
import { V36_VALID_SNAPSHOT } from './fixtures/purchasabilityV36Fixtures'
import { V31_SNAPSHOT } from './fixtures/purchasabilityV31Fixtures'

vi.mock('../../hooks/useHistoricalReliabilityForFixture', () => ({
  useHistoricalReliabilityForFixture: () => ({
    byMarketKey: {},
    loading: false,
    error: null,
  }),
}))

const FORBIDDEN = [
  'Acquistabilità V3.5',
  'LIVE SHADOW',
  'structural_v1',
  'Candidate A',
  'Candidate B',
  'Candidate C',
  'Candidate D',
  'Scarica audit V3.5',
  'Scarica dataset V3.5',
]

function baseDetail(
  overrides: Partial<CecchinoTodayDetailResponse> = {},
): CecchinoTodayDetailResponse {
  return {
    status: 'ok',
    id: 1,
    today_fixture_id: 1,
    provider_fixture_id: 100,
    scan_date: '2026-08-26',
    home_team_name: 'Home',
    away_team_name: 'Away',
    purchasability_preview_v31: V31_SNAPSHOT,
    purchasability_preview_v35: V35_VALID_SNAPSHOT,
    purchasability_v35_snapshot_status: 'valid',
    purchasability_preview_v35_v2: V36_VALID_SNAPSHOT,
    purchasability_v35_v2_snapshot_status: 'valid',
    ...overrides,
  } as CecchinoTodayDetailResponse
}

function renderDetail(detail: CecchinoTodayDetailResponse) {
  return render(
    <MemoryRouter>
      <CecchinoTodayDetailPanel detail={detail} />
    </MemoryRouter>,
  )
}

describe('CecchinoTodayDetailPanel production route V3.6', () => {
  afterEach(() => {
    cleanup()
  })

  it('mostra V3.6 e nasconde V3.5 anche se payload V3.5 valido', () => {
    renderDetail(baseDetail())
    expect(screen.getByTestId('cecchino-purchasability-v36-panel')).toBeTruthy()
    expect(screen.getByText('Indice di Acquistabilità V3.6')).toBeTruthy()
    expect(screen.queryByTestId('cecchino-purchasability-v35-panel')).toBeNull()
    const body = document.body.textContent ?? ''
    for (const s of FORBIDDEN) {
      expect(body).not.toContain(s)
    }
  })

  it('V3.1 è legacy collapsed', () => {
    renderDetail(baseDetail())
    const legacy = screen.getByTestId('purchasability-v31-legacy') as HTMLDetailsElement
    expect(legacy.open).toBe(false)
    expect(legacy.textContent).toMatch(/Versione precedente V3\.1/)
  })

  it('absent V3.6 non fa fallback a V3.5', () => {
    renderDetail(
      baseDetail({
        purchasability_preview_v35_v2: null,
        purchasability_v35_v2_snapshot_status: 'absent',
        purchasability_preview_v35: V35_VALID_SNAPSHOT,
        purchasability_v35_snapshot_status: 'valid',
      }),
    )
    expect(screen.getByTestId('v36-absent-message')).toBeTruthy()
    expect(screen.queryByTestId('cecchino-purchasability-v35-panel')).toBeNull()
    expect(document.body.textContent).not.toContain('Acquistabilità V3.5')
    expect(document.body.textContent).not.toContain('LIVE SHADOW')
  })

  it('final score senza percentuale', () => {
    renderDetail(baseDetail())
    const score = screen.getByTestId('v36-final-score')
    expect(score.textContent).toMatch(/\/ 100/)
    expect(score.textContent).not.toContain('%')
  })
})
