/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CecchinoGoalIntensityV5Panel } from './CecchinoGoalIntensityV5Panel'

vi.mock('../../lib/cecchinoTodayApi', () => ({
  getGoalIntensityV5Explanations: vi.fn(async () => ({
    status: 'ok',
    presentation: 'official_support',
    consistency_status: 'match',
    source_identity: {
      today_fixture_id: 1,
      snapshot_id: 42,
      bundle_id: 3,
      bundle_version: 'cecchino_goal_intensity_v5_official_support_bundle_v1',
    },
    index: {
      id: 'GI_A_STRICT_CORE',
      score_stored: 35.7,
      score_audit: 35.7,
      stored: 35.7,
      recomputed: 35.7,
      delta: 0,
      consistency_status: 'match',
    },
    target_heads: {
      expected_total_goals: {
        label_it: 'Stima totale gol',
        calibration_source: 'GI_E_PRIMARY_RECALIBRATED',
        stored: 2.31,
        recomputed: 2.31,
        result_stored: 2.31,
        result_audit: 2.31,
        delta: 0,
        consistency_status: 'match',
      },
      probability_goals_ge_2: {
        label_it: 'Over 1.5',
        calibration_source: 'GI_A_STRICT_CORE',
        stored: 0.692,
        recomputed: 0.692,
        delta: 0,
        consistency_status: 'match',
      },
    },
    warnings: [],
  })),
}))

afterEach(() => cleanup())

describe('CecchinoGoalIntensityV5Panel official card', () => {
  it('renders a single official card without candidate table', () => {
    render(
      <CecchinoGoalIntensityV5Panel
        goalIntensity={{
          status: 'ok',
          operational_status: 'official_support',
          operational_status_label_it: 'Supporto ufficiale',
          source: 'v5_official',
          bundle_version: 'cecchino_goal_intensity_v5_official_support_bundle_v1',
          index: { id: 'GI_A_STRICT_CORE', score: 55.2 },
          outputs: {
            expected_total_goals: { value: 2.41, calibration_source: 'GI_E_PRIMARY_RECALIBRATED' },
            over_1_5: { probability: 0.72, calibration_source: 'GI_A_STRICT_CORE' },
            under_1_5: { probability: 0.28, derived_as_complement: true },
            over_2_5: { probability: 0.48, calibration_source: 'GI_E_PRIMARY_RECALIBRATED' },
            under_2_5: { probability: 0.52, derived_as_complement: true },
            btts_yes: { probability: 0.51, calibration_source: 'GI_E_PRIMARY_RECALIBRATED' },
            btts_no: { probability: 0.49, derived_as_complement: true },
          },
          data_quality: { feature_status: 'official_v5_complete' },
        }}
      />,
    )

    expect(screen.getByTestId('goal-intensity-v5-official-card')).toBeTruthy()
    expect(screen.getByText('Intensità Goal V5')).toBeTruthy()
    expect(screen.getAllByText('Supporto ufficiale').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Non collegato ai Segnali')).toBeTruthy()
    expect(screen.getByTestId('gi-index-score').textContent).toContain('55.2')
    expect(screen.getByTestId('gi-expected-total').textContent).toContain('2.41')
    expect(screen.getByText('Over 1.5')).toBeTruthy()
    expect(screen.getByText('Under 1.5')).toBeTruthy()
    expect(screen.getByText('Over 2.5')).toBeTruthy()
    expect(screen.getByText('Under 2.5')).toBeTruthy()
    expect(screen.getByText('Gol / No Gol')).toBeTruthy()
    expect(screen.queryByText('Primary')).toBeNull()
    expect(screen.queryByText('Challenger')).toBeNull()
    expect(screen.queryByText('GI_B_RECENCY')).toBeNull()
    expect(screen.queryByText('GI_F_REGULARIZED_PILLARS')).toBeNull()
  })

  it('audit shows stored as primary and coherent badge', async () => {
    const user = userEvent.setup()
    render(
      <CecchinoGoalIntensityV5Panel
        todayFixtureId={1}
        goalIntensity={{
          status: 'ok',
          operational_status: 'official_support',
          operational_status_label_it: 'Supporto ufficiale',
          source: 'v5_official',
          index: { id: 'GI_A_STRICT_CORE', score: 35.7 },
          outputs: {
            expected_total_goals: { value: 2.31 },
            over_1_5: { probability: 0.692 },
            under_1_5: { probability: 0.308 },
            over_2_5: { probability: 0.416 },
            under_2_5: { probability: 0.584 },
            btts_yes: { probability: 0.492 },
            btts_no: { probability: 0.508 },
          },
        }}
      />,
    )
    await user.click(screen.getByRole('button', { name: /Apri audit/i }))
    await waitFor(() => expect(screen.getByTestId('gi-official-audit')).toBeTruthy())
    expect(screen.getByTestId('gi-audit-index-stored').textContent).toContain('35.70')
    expect(screen.getByText(/Stored snapshot/i)).toBeTruthy()
    expect(screen.getByText(/Ricalcolo audit/i)).toBeTruthy()
    expect(screen.getAllByText('Coerente').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('Preview research')).toBeNull()
  })

  it('shows V4 fallback and hides BTTS', () => {
    render(
      <CecchinoGoalIntensityV5Panel
        goalIntensity={{
          status: 'ok',
          operational_status: 'official_support',
          source: 'v4_fallback',
          outputs: {
            expected_total_goals: { value: 2.1 },
            over_1_5: { probability: 0.6 },
            under_1_5: { probability: 0.4 },
            over_2_5: { probability: 0.4 },
            under_2_5: { probability: 0.6 },
            btts_yes: { probability: null, unavailable: true },
            btts_no: { probability: null, unavailable: true },
          },
          fallback: {
            fallback_reason: 'official_v5_features_incomplete',
            btts_unavailable: true,
          },
        }}
      />,
    )
    expect(screen.getAllByText('Fallback V4').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('N/D').length).toBeGreaterThanOrEqual(2)
  })

  it('marks legacy archive without presenting as official', () => {
    render(
      <CecchinoGoalIntensityV5Panel
        goalIntensity={{
          status: 'ok',
          presentation: 'legacy_archive',
          legacy_archive: true,
          source: 'v5_legacy_preview',
          operational_status_label_it: 'Archivio preview',
        }}
      />,
    )
    expect(screen.getAllByText('Archivio preview').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByTestId('gi-index-score')).toBeNull()
  })
})
