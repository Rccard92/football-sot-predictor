/** @vitest-environment jsdom */
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { CecchinoGoalIntensityV5Panel } from './CecchinoGoalIntensityV5Panel'

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
