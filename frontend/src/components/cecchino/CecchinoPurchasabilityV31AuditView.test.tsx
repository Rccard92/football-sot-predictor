/** @vitest-environment jsdom */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { CecchinoFormulaAuditModal } from './CecchinoFormulaAuditModal'
import { CecchinoPurchasabilityV31AuditView } from './CecchinoPurchasabilityV31AuditView'
import {
  buildAwayV31Explanation,
  buildGateFailedV31Explanation,
  buildNonCalculableV31Explanation,
} from './fixtures/purchasabilityV31Fixtures'

afterEach(() => {
  cleanup()
})

describe('CecchinoPurchasabilityV31AuditView', () => {
  describe('score calcolato', () => {
    it('mostra sezioni principali', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      expect(screen.getByTestId('v31-section-result')).toBeTruthy()
      expect(screen.getByTestId('v31-section-gate')).toBeTruthy()
      expect(screen.getByTestId('v31-section-theoretical')).toBeTruthy()
      expect(screen.getByTestId('v31-section-penalties')).toBeTruthy()
      expect(screen.getByTestId('v31-section-historical')).toBeTruthy()
      expect(screen.getByTestId('v31-section-final')).toBeTruthy()
      expect(screen.getByTestId('v31-section-comparison')).toBeTruthy()
    })

    it('mostra score finale corretto', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      expect(screen.getByTestId('v31-score-final').textContent).toContain('52')
      expect(screen.getByTestId('v31-score-final').textContent).toContain('Media')
    })

    it('mostra gate attivato', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      expect(screen.getByTestId('v31-gate-status').textContent).toContain('Attivato')
    })

    it('mostra valore teorico', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      expect(screen.getByTestId('v31-theoretical-raw').textContent).toContain('86')
    })

    it('mostra fattore storico', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      expect(screen.getByTestId('v31-historical-factor').textContent).toContain('0,6')
    })

    it('mostra formula calcolo finale', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      const formula = screen.getByTestId('v31-final-formula')
      expect(formula.textContent).toMatch(/86/)
      expect(formula.textContent).toMatch(/0,6/)
      expect(formula.textContent).toMatch(/ROUND_HALF_UP/)
      expect(formula.textContent).toMatch(/52/)
    })

    it('mostra penalità applicate', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      const penalties = screen.getByTestId('v31-section-penalties')
      expect(within(penalties).getByTestId('v31-penalty-probability_risk')).toBeTruthy()
      expect(within(penalties).getByTestId('v31-penalty-family_ambiguity')).toBeTruthy()
      expect(within(penalties).getByTestId('v31-total-penalty').textContent).toMatch(/−12/)
    })

    it('mostra confronto con V3', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      const comparison = screen.getByTestId('v31-section-comparison')
      expect(within(comparison).getByTestId('v31-comparison-v3-score').textContent).toBe('47')
      expect(within(comparison).getByTestId('v31-comparison-v31-score').textContent).toBe('52')
      expect(within(comparison).getByTestId('v31-comparison-delta').textContent).toMatch(/\+5/)
    })
  })

  describe('gate fallito', () => {
    it('mostra "Non attivato" con motivo', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildGateFailedV31Explanation()} />)
      expect(screen.getByTestId('v31-status').textContent).toContain('Non attivato')
      expect(screen.getByTestId('v31-gate-status').textContent).toContain('Non attivato')
      expect(screen.getByTestId('v31-gate-reason').textContent).toContain('Rating sotto 50')
    })

    it('non mostra sezioni calcolo quando gate fallito', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildGateFailedV31Explanation()} />)
      expect(screen.queryByTestId('v31-section-theoretical')).toBeNull()
      expect(screen.queryByTestId('v31-section-penalties')).toBeNull()
      expect(screen.queryByTestId('v31-section-final')).toBeNull()
    })
  })

  describe('non calcolabile', () => {
    it('mostra "Non calcolabile" con motivo', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildNonCalculableV31Explanation()} />)
      expect(screen.getByTestId('v31-status').textContent).toContain('Non calcolabile')
      expect(screen.getByTestId('v31-reason').textContent).toContain('Quota mancante')
    })
  })

  describe('dettagli tecnici', () => {
    it('dettagli chiusi di default', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      const details = screen.getByTestId('v31-technical-details') as HTMLDetailsElement
      expect(details.open).toBe(false)
    })

    it('clic su summary apre dettagli', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      const summary = screen.getByTestId('v31-technical-details-summary')
      fireEvent.click(summary)
      const details = screen.getByTestId('v31-technical-details') as HTMLDetailsElement
      expect(details.open).toBe(true)
    })

    it('mostra versioni nei dettagli tecnici', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      fireEvent.click(screen.getByTestId('v31-technical-details-summary'))
      expect(screen.getByTestId('v31-candidate-version').textContent).toBe(
        'cecchino_purchasability_v31_candidate_1',
      )
      expect(screen.getByTestId('v31-formula-version').textContent).toBe(
        'cecchino_purchasability_v31_shadow_v1',
      )
      expect(screen.getByTestId('v31-audit-version').textContent).toBe(
        'cecchino_purchasability_v31_audit_v1',
      )
    })

    it('mostra nota shadow nei dettagli', () => {
      render(<CecchinoPurchasabilityV31AuditView explanation={buildAwayV31Explanation()} />)
      fireEvent.click(screen.getByTestId('v31-technical-details-summary'))
      expect(screen.getByTestId('v31-shadow-note').textContent).toMatch(/V3\.1 shadow/)
    })
  })
})

describe('CecchinoFormulaAuditModal V3.1', () => {
  it('titolo "Analisi Acquistabilità V3.1" per metric_key purchasability_v31', () => {
    const onClose = vi.fn()
    render(
      <CecchinoFormulaAuditModal
        explanation={buildAwayV31Explanation()}
        onClose={onClose}
      />,
    )
    expect(screen.getByText('Analisi Acquistabilità V3.1')).toBeTruthy()
  })

  it('mostra audit view V3.1 nel modal', () => {
    const onClose = vi.fn()
    render(
      <CecchinoFormulaAuditModal
        explanation={buildAwayV31Explanation()}
        onClose={onClose}
      />,
    )
    expect(screen.getByTestId('purchasability-v31-audit-view')).toBeTruthy()
  })

  it('Escape chiude modal', () => {
    const onClose = vi.fn()
    render(
      <CecchinoFormulaAuditModal
        explanation={buildAwayV31Explanation()}
        onClose={onClose}
      />,
    )
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('metrica label mostra "Acquistabilità V3.1"', () => {
    const onClose = vi.fn()
    render(
      <CecchinoFormulaAuditModal
        explanation={buildAwayV31Explanation()}
        onClose={onClose}
      />,
    )
    expect(screen.getAllByText('Acquistabilità V3.1').length).toBeGreaterThan(0)
  })
})
