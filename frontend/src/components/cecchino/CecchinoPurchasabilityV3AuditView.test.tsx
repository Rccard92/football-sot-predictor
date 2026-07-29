/** @vitest-environment jsdom */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CecchinoFormulaAuditModal } from './CecchinoFormulaAuditModal'
import { CecchinoPurchasabilityV3AuditView } from './CecchinoPurchasabilityV3AuditView'
import { buildAwayV3Explanation } from './fixtures/purchasabilityV3AwayRegression'

afterEach(() => {
  cleanup()
})

describe('CecchinoPurchasabilityV3AuditView', () => {
  const explanation = buildAwayV3Explanation()

  it('mostra risultato semplice, gate, value, penalità, famiglia, opposto, linked, finale, diagnostica', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={explanation} />)
    expect(screen.getByTestId('v3-section-result')).toBeTruthy()
    expect(screen.getByTestId('v3-section-gate')).toBeTruthy()
    expect(screen.getByTestId('v3-section-value')).toBeTruthy()
    expect(screen.getByTestId('v3-section-penalties')).toBeTruthy()
    expect(screen.getByTestId('v3-section-family')).toBeTruthy()
    expect(screen.getByTestId('v3-section-opposite')).toBeTruthy()
    expect(screen.getByTestId('v3-section-linked')).toBeTruthy()
    expect(screen.getByTestId('v3-section-final')).toBeTruthy()
    expect(screen.getByTestId('v3-section-diagnostics')).toBeTruthy()
  })

  it('scala Edge e value score', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={explanation} />)
    expect(screen.getByTestId('v3-edge-scale').textContent).toContain('50%+')
    expect(screen.getByTestId('v3-section-value').textContent).toContain('100')
    expect(screen.getByTestId('v3-section-value').textContent).toMatch(/clamp/i)
  })

  it('penalità con segno negativo e totali qualità', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={explanation} />)
    expect(screen.getByTestId('v3-penalty-probability_risk')).toBeTruthy()
    expect(screen.getByTestId('v3-penalty-opposite_market_pressure')).toBeTruthy()
    expect(screen.getByTestId('v3-penalty-extreme_divergence')).toBeTruthy()
    expect(screen.getByTestId('v3-penalty-family_ambiguity')).toBeTruthy()
    expect(screen.getByTestId('v3-penalty-quote_quality')).toBeTruthy()
    expect(screen.getByTestId('v3-penalty-points-opposite_market_pressure').textContent).toMatch(
      /^−/,
    )
    expect(screen.getByTestId('v3-total-penalty').textContent).toMatch(/^−/)
    expect(screen.getByTestId('v3-quality-start').textContent).toContain('100')
    expect(screen.getByTestId('v3-quality-final').textContent).toMatch(/46/)
  })

  it('famiglia 1X2 e X2 diagnostico non concorrente', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={explanation} />)
    expect(screen.getByTestId('v3-family-row-HOME')).toBeTruthy()
    expect(screen.getByTestId('v3-family-row-DRAW')).toBeTruthy()
    expect(screen.getByTestId('v3-family-row-AWAY')).toBeTruthy()
    expect(screen.queryByTestId('v3-family-row-X_TWO')).toBeNull()
    expect(screen.getByTestId('v3-x2-diagnostic-note').textContent).toMatch(/contesto collegato/i)
  })

  it('calcolo finale value × quality senza media geometrica', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={explanation} />)
    const final = screen.getByTestId('v3-section-final')
    expect(final.textContent).toMatch(/value × quality|× 46|ROUND_HALF_UP/i)
    expect(final.textContent).not.toMatch(/√\s*\(|sqrt\s*\(/i)
    expect(screen.getByTestId('v3-no-geometric-mean').textContent).toMatch(
      /nessuna media geometrica/i,
    )
  })

  it('regression AWAY score 47', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={explanation} />)
    expect(screen.getByTestId('v3-persisted-result').textContent).toContain('47')
    expect(screen.getByTestId('v3-section-result').textContent).toContain('47')
    expect(screen.getByTestId('v3-section-result').textContent).toMatch(/Media/)
  })

  it('badge fixed scales / no historical / parallel warning / consistency', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={explanation} />)
    const badges = screen.getByTestId('v3-badges').textContent || ''
    expect(badges).toMatch(/Scale fisse/)
    expect(badges).toMatch(/Nessun profilo storico/)
    expect(badges).toMatch(/V3 parallela/)
    expect(screen.getByTestId('v3-parallel-warning').textContent).toMatch(/candidato parallelo/i)
    expect(screen.getByTestId('v3-consistency').textContent).toMatch(/rounding_match|match/)
    expect(screen.getByTestId('v3-audit-result').textContent).toMatch(/46/)
  })

  it('gate fallito: Indice non attivato', () => {
    const failed = buildAwayV3Explanation({
      gate: {
        gate_status: 'failed_non_positive_edge',
        edge_positive: false,
        probability_advantage_positive: true,
        gate_reason_codes: ['non_positive_edge'],
      },
      final_calculation: { score: null, class: null, formula_steps: [] },
      persisted_result: { score: null, gate_status: 'failed_non_positive_edge' },
      stored_result: null,
      stored_result_display: 'Indice non attivato',
    })
    render(<CecchinoPurchasabilityV3AuditView explanation={failed} />)
    expect(screen.getByTestId('v3-gate-not-activated')).toBeTruthy()
    expect(screen.queryByTestId('v3-section-value')).toBeNull()
    expect(screen.queryByTestId('v3-section-penalties')).toBeNull()
  })

  it('famiglia Goal e doppia chance isolate', () => {
    const goals = buildAwayV3Explanation({
      market_key: 'OVER_2_5',
      market_label: 'Over 2.5',
      family_comparison: {
        market_family: 'GOALS_FT_2_5',
        family_competitors: ['UNDER_2_5'],
        gate_passed_family_competitors: ['UNDER_2_5'],
        best_family_market_by_edge: 'OVER_2_5',
        selected_is_family_edge_leader: true,
        selected_edge: 20,
        best_other_edge: 5,
        edge_gap_or_deficit: 15,
        ambiguity_status: 'leader_clear',
      },
      linked_market_context: null,
    })
    const { rerender } = render(<CecchinoPurchasabilityV3AuditView explanation={goals} />)
    expect(screen.getByTestId('v3-family-row-OVER_2_5')).toBeTruthy()
    expect(screen.getByTestId('v3-family-row-UNDER_2_5')).toBeTruthy()
    expect(screen.queryByTestId('v3-family-row-HOME')).toBeNull()

    const dc = buildAwayV3Explanation({
      market_key: 'ONE_X',
      market_label: '1X',
      family_comparison: {
        market_family: 'DOUBLE_CHANCE',
        family_competitors: ['X_TWO', 'ONE_TWO'],
        gate_passed_family_competitors: ['X_TWO'],
        best_family_market_by_edge: 'ONE_X',
        selected_is_family_edge_leader: true,
        selected_edge: 15,
        ambiguity_status: 'leader_clear',
      },
      linked_market_context: null,
    })
    rerender(<CecchinoPurchasabilityV3AuditView explanation={dc} />)
    expect(screen.getByTestId('v3-family-row-ONE_X')).toBeTruthy()
    expect(screen.getByTestId('v3-family-row-X_TWO')).toBeTruthy()
    expect(screen.getByTestId('v3-family-row-ONE_TWO')).toBeTruthy()
    expect(screen.queryByTestId('v3-family-row-AWAY')).toBeNull()
  })
})

describe('CecchinoFormulaAuditModal V3 a11y', () => {
  it('dialog Escape e ruolo accessibile', () => {
    const onClose = vi.fn()
    render(
      <CecchinoFormulaAuditModal
        explanation={buildAwayV3Explanation()}
        onClose={onClose}
      />,
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
