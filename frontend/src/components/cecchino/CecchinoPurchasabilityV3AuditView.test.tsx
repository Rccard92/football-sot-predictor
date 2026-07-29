/** @vitest-environment jsdom */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CecchinoFormulaAuditModal } from './CecchinoFormulaAuditModal'
import { CecchinoPurchasabilityV3AuditView } from './CecchinoPurchasabilityV3AuditView'
import {
  buildAwayV3Explanation,
  buildDrawV3Explanation,
  MATCH_WINNER_FAMILY_ROWS,
} from './fixtures/purchasabilityV3AwayRegression'

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
        gate_reading: 'Indice non attivato: valore positivo non presente (Edge non positivo).',
      },
      final_calculation: { score: null, class: null, formula_steps: [] },
      persisted_result: { score: null, gate_status: 'failed_non_positive_edge' },
      stored_result: null,
      stored_result_display: 'Indice non attivato',
    })
    render(<CecchinoPurchasabilityV3AuditView explanation={failed} />)
    expect(screen.getByTestId('v3-gate-reading').textContent).toMatch(/non attivato/i)
    expect(screen.queryByTestId('v3-section-value')).toBeNull()
    expect(screen.queryByTestId('v3-section-penalties')).toBeNull()
  })

  it('famiglia Goal e doppia chance isolate via market_rows', () => {
    const goals = buildAwayV3Explanation({
      market_key: 'OVER_2_5',
      market_label: 'Over 2.5',
      market_family: 'GOALS_FT_2_5',
      market_family_label: 'Goal FT 2.5',
      family_comparison: {
        market_family: 'GOALS_FT_2_5',
        market_family_label: 'Goal FT 2.5',
        family_competitors: ['UNDER_2_5'],
        gate_passed_family_competitors: ['UNDER_2_5'],
        best_family_market_by_edge: 'OVER_2_5',
        selected_is_family_edge_leader: true,
        selected_edge: 20,
        best_other_edge: 5,
        edge_gap_or_deficit: 15,
        ambiguity_status: 'leader_clear',
        market_rows: [
          {
            market_key: 'OVER_2_5',
            market_label: 'Over 2.5',
            edge_pct: 20,
            gate_status: 'passed',
            gate_passed: true,
            is_selected: true,
            is_leader: true,
            rank_by_edge: 1,
            included_in_gate_passed_comparison: true,
            score: 20,
            edge_diff_from_leader: 0,
          },
          {
            market_key: 'UNDER_2_5',
            market_label: 'Under 2.5',
            edge_pct: 5,
            gate_status: 'passed',
            gate_passed: true,
            is_selected: false,
            is_leader: false,
            rank_by_edge: 2,
            included_in_gate_passed_comparison: true,
            score: 12,
            edge_diff_from_leader: -15,
          },
        ],
      },
      linked_market_context: null,
    })
    const { rerender } = render(<CecchinoPurchasabilityV3AuditView explanation={goals} />)
    expect(screen.getByTestId('v3-family-row-OVER_2_5')).toBeTruthy()
    expect(screen.getByTestId('v3-family-row-UNDER_2_5')).toBeTruthy()
    expect(screen.queryByTestId('v3-family-row-HOME')).toBeNull()
    expect(screen.getByTestId('v3-family-edge-UNDER_2_5').textContent).toMatch(/5/)

    const dc = buildAwayV3Explanation({
      market_key: 'ONE_X',
      market_label: '1X',
      market_family: 'DOUBLE_CHANCE',
      market_family_label: 'Doppia chance',
      family_comparison: {
        market_family: 'DOUBLE_CHANCE',
        market_family_label: 'Doppia chance',
        family_competitors: ['X_TWO', 'ONE_TWO'],
        gate_passed_family_competitors: ['X_TWO'],
        best_family_market_by_edge: 'ONE_X',
        selected_is_family_edge_leader: true,
        selected_edge: 15,
        ambiguity_status: 'leader_clear',
        market_rows: [
          {
            market_key: 'ONE_X',
            market_label: '1X',
            edge_pct: 15,
            gate_passed: true,
            is_selected: true,
            is_leader: true,
            rank_by_edge: 1,
            included_in_gate_passed_comparison: true,
            score: 30,
            edge_diff_from_leader: 0,
          },
          {
            market_key: 'X_TWO',
            market_label: 'X2',
            edge_pct: 10,
            gate_passed: true,
            is_selected: false,
            is_leader: false,
            rank_by_edge: 2,
            included_in_gate_passed_comparison: true,
            score: 50,
            edge_diff_from_leader: -5,
          },
          {
            market_key: 'ONE_TWO',
            market_label: '12',
            edge_pct: -2,
            gate_passed: false,
            is_selected: false,
            is_leader: false,
            rank_by_edge: 3,
            included_in_gate_passed_comparison: false,
            score: null,
            edge_diff_from_leader: -17,
          },
        ],
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

describe('STEP 2.1 audit hardening', () => {
  it('mostra famiglia umana e codice tecnico', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={buildAwayV3Explanation()} />)
    expect(screen.getByTestId('v3-family-label').textContent).toBe('Esito finale 1/X/2')
    expect(screen.getByTestId('v3-family-code').textContent).toBe('MATCH_WINNER_FT')
  })

  it('versioni distinte senza fallback candidate←formula', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={buildAwayV3Explanation()} />)
    expect(screen.getByTestId('v3-candidate-version').textContent).toBe(
      'cecchino_purchasability_v3_candidate_1',
    )
    expect(screen.getByTestId('v3-formula-version').textContent).toBe(
      'cecchino_purchasability_v3_fixed_discount_v1',
    )
    expect(screen.getByTestId('v3-audit-version').textContent).toBe(
      'cecchino_purchasability_v3_audit_v1',
    )
    const noCandidate = buildAwayV3Explanation({
      candidate_version: undefined,
      input: { ...(buildAwayV3Explanation().input as object), candidate_version: undefined },
    })
    cleanup()
    render(<CecchinoPurchasabilityV3AuditView explanation={noCandidate} />)
    expect(screen.getByTestId('v3-candidate-version').textContent).toBe('—')
    expect(screen.getByTestId('v3-formula-version').textContent).toBe(
      'cecchino_purchasability_v3_fixed_discount_v1',
    )
  })

  it('metadata generated_at e source_snapshot_at', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={buildAwayV3Explanation()} />)
    expect(screen.getByTestId('v3-generated-at').textContent).toContain('2026-07-28')
    expect(screen.getByTestId('v3-source-snapshot-at').textContent).toContain('2026-07-28')
    cleanup()
    render(
      <CecchinoPurchasabilityV3AuditView
        explanation={buildAwayV3Explanation({
          generated_at: null,
          source_snapshot_at: null,
          data_origin: {
            ...(buildAwayV3Explanation().data_origin as object),
            generated_at: null,
            source_snapshot_at: null,
          },
        })}
      />,
    )
    expect(screen.getByTestId('v3-generated-at').textContent).toBe('—')
    expect(screen.getByTestId('v3-source-snapshot-at').textContent).toBe('—')
  })

  it('tabella famiglia usa market_rows con Edge reali e nessun -43,04', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={buildAwayV3Explanation()} />)
    expect(screen.getByTestId('v3-family-table')).toBeTruthy()
    expect(screen.getByTestId('v3-family-edge-AWAY').textContent).toMatch(/83[,.]04/)
    expect(screen.getByTestId('v3-family-edge-DRAW').textContent).toMatch(/20/)
    expect(screen.getByTestId('v3-family-edge-HOME').textContent).toMatch(/-30[,.]59|−30[,.]59/)
    expect(screen.getByTestId('v3-family-leader-badge-AWAY')).toBeTruthy()
    const text = screen.getByTestId('v3-family-table').textContent || ''
    expect(text).not.toMatch(/-43[,.]04|−43[,.]04/)
    expect(MATCH_WINNER_FAMILY_ROWS.find((r) => r.market_key === 'AWAY')?.score).toBe(47)
  })

  it('DRAW non ricostruisce Edge leader: diff -63,04', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={buildDrawV3Explanation()} />)
    expect(screen.getByTestId('v3-family-edge-AWAY').textContent).toMatch(/83[,.]04/)
    expect(screen.getByTestId('v3-family-edge-DRAW').textContent).toMatch(/20/)
    expect(screen.getByTestId('v3-family-diff-DRAW').textContent).toMatch(/-63[,.]04|−63[,.]04/)
    expect(screen.getByTestId('v3-score-final').textContent).toContain('11')
  })

  it('input tecnici chiusi di default e summary accessibile', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={buildAwayV3Explanation()} />)
    const details = screen.getByTestId('v3-raw-inputs-details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    const summary = screen.getByTestId('v3-raw-inputs-summary')
    expect(summary.tagName).toBe('SUMMARY')
    expect(summary.textContent).toMatch(/dati tecnici grezzi/i)
    fireEvent.click(summary)
    expect(details.open).toBe(true)
  })

  it('reading_short e reading_detailed non duplicati', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={buildAwayV3Explanation()} />)
    expect(screen.getByTestId('v3-reading-short')).toBeTruthy()
    expect(screen.getByTestId('v3-reading-detailed')).toBeTruthy()
    expect(screen.queryByTestId('v3-reading-detailed-inline')).toBeTruthy()
    const identical = buildAwayV3Explanation({
      reading_short: 'Stesso testo',
      reading_detailed: 'Stesso testo',
    })
    cleanup()
    render(<CecchinoPurchasabilityV3AuditView explanation={identical} />)
    expect(screen.getByTestId('v3-reading-short').textContent).toBe('Stesso testo')
    expect(screen.queryByTestId('v3-reading-detailed-inline')).toBeNull()
    expect(screen.getByTestId('v3-reading-detailed').textContent).toBe('Stesso testo')
  })

  it('quota derivata badge e testo Betfair', () => {
    const derived = buildAwayV3Explanation({
      derived_quote: true,
      diagnostic_only: true,
      input: {
        ...(buildAwayV3Explanation().input as object),
        performance_type: 'derived',
        not_real_book_quote: true,
        diagnostic_only: true,
      },
    })
    render(<CecchinoPurchasabilityV3AuditView explanation={derived} />)
    expect(screen.getByTestId('v3-badge-derived').textContent).toMatch(/Quota derivata/)
    expect(screen.getByTestId('v3-badge-diagnostic').textContent).toMatch(/Solo diagnostico/)
    expect(screen.getByTestId('v3-derived-quote-note').textContent).toMatch(
      /non rappresenta una quota Betfair/i,
    )
  })

  it('stati gate semantici senza reinterpretazione FE', () => {
    const unsupported = buildAwayV3Explanation({
      gate: {
        gate_status: 'unsupported_market',
        gate_reading: "Mercato non supportato dall'Acquistabilità V3.",
      },
      final_calculation: { score: null, formula_steps: [] },
      persisted_result: { score: null, gate_status: 'unsupported_market' },
      stored_result: null,
    })
    render(<CecchinoPurchasabilityV3AuditView explanation={unsupported} />)
    const reading = screen.getByTestId('v3-gate-reading').textContent || ''
    expect(reading).toMatch(/non supportato/i)
    expect(reading.toLowerCase()).not.toMatch(/nessun valore positivo/)
    cleanup()

    const unavailable = buildAwayV3Explanation({
      gate: {
        gate_status: 'unavailable_inputs',
        gate_reading:
          'Indice non calcolabile: uno o più input obbligatori non sono disponibili.',
      },
      final_calculation: { score: null, formula_steps: [] },
      persisted_result: { score: null, gate_status: 'unavailable_inputs' },
      stored_result: null,
    })
    render(<CecchinoPurchasabilityV3AuditView explanation={unavailable} />)
    expect(screen.getByTestId('v3-gate-reading').textContent).toMatch(/non calcolabile/i)
  })

  it('score AWAY 47 e formula invariata', () => {
    render(<CecchinoPurchasabilityV3AuditView explanation={buildAwayV3Explanation()} />)
    expect(screen.getByTestId('v3-score-final').textContent).toContain('47')
    expect(screen.getByTestId('v3-no-geometric-mean').textContent).toMatch(
      /value × quality \/ 100/i,
    )
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
    expect(screen.getByTestId('audit-modal-candidate-badge')).toBeTruthy()
    expect(screen.getByTestId('audit-modal-formula-badge')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
