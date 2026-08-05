import { describe, expect, it } from 'vitest'
import {
  isHistoricalBudgetStop,
  isProviderQuotaExhausted,
  scanJobTitle,
} from './CecchinoTodayScanProgressCard'
import type { CecchinoTodayScanJob } from '../../lib/cecchinoTodayApi'

function job(overrides: Partial<CecchinoTodayScanJob> = {}): CecchinoTodayScanJob {
  return {
    job_id: 'j1',
    scan_date: '2026-08-08',
    timezone: 'Europe/Rome',
    force_rescan: false,
    status: 'completed',
    current_step: 'completed',
    progress_current: 10,
    progress_total: 10,
    progress_pct: 100,
    fixtures_found: 10,
    fixtures_checked: 10,
    odds_checked: 10,
    eligible_count: 3,
    excluded_count: 7,
    excluded_summary: {},
    result_summary: {
      api_calls_total: 1200,
      execution_date: '2026-08-06',
      scan_date: '2026-08-08',
    },
    warnings: [],
    errors: [],
    started_at: null,
    finished_at: null,
    ...overrides,
  }
}

describe('CecchinoTodayScanProgressCard status labels', () => {
  it('mostra quota provider esaurita', () => {
    expect(isProviderQuotaExhausted('provider_quota_exhausted')).toBe(true)
    expect(scanJobTitle(job({ status: 'provider_quota_exhausted' }))).toBe(
      'Scansione interrotta: richieste API esaurite',
    )
  })

  it('etichetta stati storici budget come vecchio arresto', () => {
    expect(isHistoricalBudgetStop('partial_stopped_budget')).toBe(true)
    expect(scanJobTitle(job({ status: 'partial_stopped_budget' }))).toBe(
      'Vecchio arresto preventivo per budget locale',
    )
    expect(scanJobTitle(job({ status: 'failed_budget_guard' }))).toBe(
      'Vecchio arresto preventivo per budget locale',
    )
  })

  it('job sopra 1000 chiamate completed non appare interrotto', () => {
    expect(scanJobTitle(job({ status: 'completed' }))).toBe('Scansione completata')
  })

  it('distingue scan_date ed execution_date nel summary', () => {
    const j = job()
    expect(j.result_summary?.scan_date).toBe('2026-08-08')
    expect(j.result_summary?.execution_date).toBe('2026-08-06')
  })
})
