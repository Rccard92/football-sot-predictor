/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { CecchinoTodayScanJob, CecchinoTodayScanReport } from '../../lib/cecchinoTodayApi'
import {
  formatBookCoveragePct,
  getScanJobBookCoverage,
} from '../../lib/cecchinoTodayApi'
import { CecchinoTodayBookCoveragePanel } from './CecchinoTodayBookCoveragePanel'
import { CecchinoTodayScanProgressCard } from './CecchinoTodayScanProgressCard'
import { CecchinoTodayScanSummary } from './CecchinoTodayScanSummary'

afterEach(() => cleanup())

function job(overrides: Partial<CecchinoTodayScanJob> = {}): CecchinoTodayScanJob {
  return {
    job_id: 'j1',
    scan_date: '2026-08-08',
    timezone: 'Europe/Rome',
    force_rescan: false,
    status: 'running',
    current_step: 'fetching_odds',
    progress_current: 2,
    progress_total: 10,
    progress_pct: 20,
    fixtures_found: 10,
    fixtures_checked: 2,
    odds_checked: 1,
    eligible_count: 0,
    excluded_count: 1,
    excluded_summary: {},
    result_summary: {
      scan_date: '2026-08-08',
      execution_date: '2026-08-08',
    },
    warnings: [],
    errors: [],
    started_at: '2026-08-08T10:00:00Z',
    finished_at: null,
    ...overrides,
  }
}

describe('getScanJobBookCoverage / formatBookCoveragePct', () => {
  it('formatta coverage con 1 decimale IT', () => {
    expect(formatBookCoveragePct(86.7)).toBe('86,7%')
    expect(formatBookCoveragePct(97.5)).toBe('97,5%')
    expect(formatBookCoveragePct(null)).toBeNull()
  })

  it('total zero → coverage null', () => {
    const cov = getScanJobBookCoverage({})
    expect(cov.hasQuoteData).toBe(false)
    expect(cov.coveragePct).toBeNull()
  })
})

describe('CecchinoTodayBookCoveragePanel', () => {
  it('mostra attesa quando nessuna quota processata', () => {
    render(<CecchinoTodayBookCoveragePanel summary={{}} />)
    expect(screen.getByTestId('book-coverage-waiting').textContent).toBe(
      'In attesa del controllo quote',
    )
    expect(screen.queryByTestId('book-coverage-pct')).toBeNull()
  })

  it('mostra Betfair + Bet365 + missing + coverage + fixture fallback', () => {
    render(
      <CecchinoTodayBookCoveragePanel
        summary={{
          betfair_primary_selection_count: 428,
          bet365_fallback_selection_count: 37,
          book_still_missing_after_fallback: 12,
          bet365_fallback_fixture_count: 18,
          book_coverage_pct: 97.5,
        }}
      />,
    )
    expect(screen.getByText('Copertura selection Book — fixture arrivate alla fase KPI')).toBeTruthy()
    expect(
      screen.getByText('Conteggio selection canoniche Book (una volta per fixture stats-qualified)'),
    ).toBeTruthy()
    expect(screen.getByTestId('book-coverage-betfair').textContent).toBe('428')
    expect(screen.getByTestId('book-coverage-bet365').textContent).toBe('37')
    expect(screen.getByTestId('book-coverage-missing').textContent).toBe('12')
    expect(screen.getByTestId('book-coverage-pct').textContent).toBe('97,5%')
    expect(screen.getByTestId('book-coverage-fixture-fallback').textContent).toBe('18')
  })

  it('mostra policy meta nel riepilogo', () => {
    render(
      <CecchinoTodayBookCoveragePanel
        showPolicyMeta
        summary={{
          betfair_primary_selection_count: 10,
          bet365_fallback_selection_count: 3,
          book_still_missing_after_fallback: 2,
          book_coverage_pct: 86.7,
          book_policy_version: 'betfair_primary_bet365_fallback_v1',
        }}
      />,
    )
    expect(screen.getByTestId('book-coverage-policy').textContent).toContain(
      'Betfair primario · Bet365 fallback',
    )
    expect(screen.getByTestId('book-coverage-version').textContent).toContain(
      'betfair_primary_bet365_fallback_v1',
    )
  })
})

describe('CecchinoTodayScanProgressCard book coverage', () => {
  it('waiting state durante scan senza quote', () => {
    render(<CecchinoTodayScanProgressCard job={job()} />)
    expect(screen.getByTestId('book-coverage-waiting')).toBeTruthy()
  })

  it('aggiorna con nuovi dati job', () => {
    const { rerender } = render(
      <CecchinoTodayScanProgressCard
        job={job({
          result_summary: {
            betfair_primary_selection_count: 10,
            bet365_fallback_selection_count: 0,
            book_still_missing_after_fallback: 0,
            book_coverage_pct: 100,
            bet365_fallback_fixture_count: 0,
          },
        })}
      />,
    )
    expect(screen.getByTestId('book-coverage-betfair').textContent).toBe('10')

    rerender(
      <CecchinoTodayScanProgressCard
        job={job({
          odds_checked: 5,
          result_summary: {
            betfair_primary_selection_count: 428,
            bet365_fallback_selection_count: 37,
            book_still_missing_after_fallback: 12,
            bet365_fallback_fixture_count: 18,
            book_coverage_pct: 97.5,
          },
        })}
      />,
    )
    expect(screen.getByTestId('book-coverage-betfair').textContent).toBe('428')
    expect(screen.getByTestId('book-coverage-bet365').textContent).toBe('37')
    expect(screen.getByTestId('book-coverage-pct').textContent).toBe('97,5%')
    expect(screen.getByTestId('book-coverage-fixture-fallback').textContent).toBe('18')
  })

  it('layout mobile: panel presente', () => {
    render(
      <CecchinoTodayScanProgressCard
        job={job({
          result_summary: {
            betfair_primary_selection_count: 1,
            bet365_fallback_selection_count: 0,
            book_still_missing_after_fallback: 0,
            book_coverage_pct: 100,
          },
        })}
      />,
    )
    const panel = screen.getByTestId('cecchino-book-coverage-panel')
    expect(panel.className).toMatch(/grid/)
  })
})

describe('CecchinoTodayScanSummary book coverage', () => {
  function report(
    result_summary?: CecchinoTodayScanReport['result_summary'],
  ): CecchinoTodayScanReport {
    return {
      status: 'completed',
      version: '1',
      scan_date: '2026-08-08',
      total_discovered: 10,
      eligible: 3,
      excluded: {},
      warnings: [],
      result_summary,
    }
  }

  it('mostra dati finali e policy', () => {
    render(
      <CecchinoTodayScanSummary
        report={report({
          betfair_primary_selection_count: 428,
          bet365_fallback_selection_count: 37,
          book_still_missing_after_fallback: 12,
          bet365_fallback_fixture_count: 18,
          book_coverage_pct: 97.5,
          book_policy_version: 'betfair_primary_bet365_fallback_v1',
        })}
      />,
    )
    expect(screen.getByTestId('book-coverage-betfair').textContent).toBe('428')
    expect(screen.getByTestId('book-coverage-pct').textContent).toBe('97,5%')
    expect(screen.getByTestId('book-coverage-policy')).toBeTruthy()
    expect(screen.getByTestId('book-coverage-version').textContent).toContain(
      'betfair_primary_bet365_fallback_v1',
    )
  })

  it('job legacy senza metriche: attesa, nessuna crash', () => {
    render(<CecchinoTodayScanSummary report={report({ fixtures_found: 5 })} />)
    expect(screen.getByTestId('book-coverage-waiting').textContent).toBe(
      'In attesa del controllo quote',
    )
    expect(screen.getByTestId('book-coverage-policy')).toBeTruthy()
  })
})
