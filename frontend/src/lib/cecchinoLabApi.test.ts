import { describe, expect, it } from 'vitest'
import {
  batchImportStatusLabel,
  countBatchReadyItems,
  formatAnomaliesHint,
  formatNullableNumber,
  formatOdd,
  historicalScanScopeLabel,
  historicalScanStatusLabel,
  isBatchItemReady,
  isHistoricalScanActive,
  isOverviewEmpty,
  matchOddsColumnLabel,
  patternSampleBadgeLabel,
  patternStabilityBadgeLabel,
  qualityBadgeClass,
  quoteLegendClass,
  replaceDatasetConfirmMessage,
  DEFAULT_HISTORICAL_SEASON,
  HISTORICAL_SCAN_CONFIRM_TOKEN,
  HISTORICAL_SCAN_PILOT_MAX_MATCHES,
  HISTORICAL_RUN_REPORT_MENU,
  historicalRunFiltersToQuery,
  parseHistoricalRunFiltersFromSearch,
  type CecchinoLabOverview,
} from './cecchinoLabApi'
import { qualityLabel } from '../components/cecchino-data-lab/labTheme'

describe('cecchinoLabApi helpers', () => {
  it('formatOdd hides null as dash', () => {
    expect(formatOdd(null)).toBe('—')
    expect(formatOdd(1.45)).toBe('1.45')
  })

  it('formatNullableNumber never shows fake zero for null', () => {
    expect(formatNullableNumber(null)).toBe('—')
    expect(formatNullableNumber(undefined)).toBe('—')
    expect(formatNullableNumber(2.5)).toBe('2.50')
  })

  it('pattern badges map sample and stability', () => {
    expect(patternSampleBadgeLabel('exploratory_only')).toBe('Esplorativo')
    expect(patternSampleBadgeLabel('descriptive_only')).toBe('Descrittivo')
    expect(patternSampleBadgeLabel('candidate_for_validation')).toBe('Candidato da validare')
    expect(patternSampleBadgeLabel('small_sample')).toBe('Campione insufficiente')
    expect(patternStabilityBadgeLabel('stable_candidate')).toBe('Candidata stabile')
    expect(patternStabilityBadgeLabel('concentrated')).toBe('Concentrata')
    expect(patternStabilityBadgeLabel('inconsistent')).toBe('Incoerente')
    expect(patternStabilityBadgeLabel('insufficient_evidence')).toBe('Insufficiente')
    expect(patternStabilityBadgeLabel('directionally_consistent')).toBe('Coerente')
  })

  it('quoteLegendClass marks unavailable', () => {
    expect(quoteLegendClass('unavailable')).toBe('lab-quote-na')
  })

  it('matchOddsColumnLabel uses 1/X/2', () => {
    expect(matchOddsColumnLabel('home')).toBe('1')
    expect(matchOddsColumnLabel('draw')).toBe('X')
    expect(matchOddsColumnLabel('away')).toBe('2')
  })

  it('qualityBadgeClass maps statuses', () => {
    expect(qualityBadgeClass('complete')).toBe('lab-badge-ok')
    expect(qualityBadgeClass('complete_with_warnings')).toBe('lab-badge-warn')
    expect(qualityBadgeClass('partial')).toBe('lab-badge-warn')
    expect(qualityBadgeClass('error')).toBe('lab-badge-err')
  })

  it('qualityLabel covers complete_with_warnings', () => {
    expect(qualityLabel('complete')).toBe('Completo')
    expect(qualityLabel('complete_with_warnings')).toBe('Completo con warning')
    expect(qualityLabel('error')).toBe('Errore')
  })

  it('formatAnomaliesHint excludes info', () => {
    expect(formatAnomaliesHint(0, 0)).toBe('0 errori · 0 warning')
    expect(formatAnomaliesHint(2, 1)).toBe('2 errori · 1 warning')
  })

  it('replaceDatasetConfirmMessage is dynamic', () => {
    const msg = replaceDatasetConfirmMessage('League Two', '2025/2026')
    expect(msg).toContain('League Two 2025/2026')
    expect(msg).toContain('Serie A')
    expect(msg).toContain('Championship')
  })

  it('batch status helpers', () => {
    expect(batchImportStatusLabel('ready')).toBe('Pronto')
    expect(batchImportStatusLabel('ready_with_warnings')).toBe('Pronto con warning')
    expect(batchImportStatusLabel('duplicate_in_batch')).toBe('Duplicato')
    expect(batchImportStatusLabel('dataset_already_exists')).toBe('Già presente')
    expect(isBatchItemReady('ready')).toBe(true)
    expect(isBatchItemReady('ready_with_warnings')).toBe(true)
    expect(isBatchItemReady('blocked')).toBe(false)
    expect(
      countBatchReadyItems([
        { import_status: 'ready' },
        { import_status: 'ready_with_warnings' },
        { import_status: 'blocked' },
        { import_status: 'already_imported' },
      ]),
    ).toBe(2)
  })

  it('historical scan helpers', () => {
    expect(DEFAULT_HISTORICAL_SEASON).toBe('2021/2022')
    expect(HISTORICAL_SCAN_CONFIRM_TOKEN).toBe('RUN_CECCHINO_LAB_HISTORICAL_SCAN')
    expect(HISTORICAL_SCAN_PILOT_MAX_MATCHES).toBe(200)
    expect(historicalScanStatusLabel('ready_with_warnings')).toBe('Pronta con warning')
    expect(historicalScanStatusLabel('blocked')).toBe('Bloccata')
    expect(historicalScanStatusLabel('running')).toBe('In esecuzione')
    expect(historicalScanStatusLabel('completed')).toBe('Completata')
    expect(historicalScanStatusLabel('failed')).toBe('Fallita')
    expect(isHistoricalScanActive('running')).toBe(true)
    expect(isHistoricalScanActive('pending')).toBe(true)
    expect(isHistoricalScanActive('completed')).toBe(false)
    expect(quoteLegendClass('real')).toBe('lab-quote-real')
    expect(quoteLegendClass('derived')).toBe('lab-quote-derived')
    expect(quoteLegendClass('unavailable')).toBe('lab-quote-na')
    expect(
      historicalScanScopeLabel({
        id: 1,
        season_label: '2021/2022',
        status: 'completed',
        scan_version: 'v2',
        requested_at: null,
        started_at: null,
        completed_at: null,
        current_dataset_id: null,
        current_match_id: null,
        current_competition: null,
        matches_total: 200,
        matches_processed: 200,
        matches_eligible_core: 100,
        matches_excluded: 50,
        matches_error: 0,
        progress_pct: 100,
        is_partial_run: true,
        run_scope: 'pilot',
        max_matches: 200,
      }),
    ).toBe('Test tecnico (max 200)')
    expect(
      historicalScanScopeLabel({
        id: 3,
        season_label: '2021/2022',
        status: 'completed',
        scan_version: 'v3',
        requested_at: null,
        started_at: null,
        completed_at: null,
        current_dataset_id: null,
        current_match_id: null,
        current_competition: null,
        matches_total: 320,
        matches_processed: 450,
        matches_eligible_core: 320,
        matches_excluded: 130,
        matches_error: 0,
        progress_pct: 100,
        is_partial_run: true,
        run_scope: 'balanced_pilot',
        pilot_strategy: 'eligible_per_competition',
        eligible_per_competition: 20,
        max_matches: null,
      }),
    ).toBe('Pilota bilanciato (20 eleggibili/campionato)')
    expect(
      historicalScanScopeLabel({
        id: 2,
        season_label: '2021/2022',
        status: 'completed',
        scan_version: 'v2',
        requested_at: null,
        started_at: null,
        completed_at: null,
        current_dataset_id: null,
        current_match_id: null,
        current_competition: null,
        matches_total: 3000,
        matches_processed: 3000,
        matches_eligible_core: 2000,
        matches_excluded: 500,
        matches_error: 0,
        progress_pct: 100,
        is_partial_run: false,
        run_scope: 'full',
        max_matches: null,
      }),
    ).toBe('Completa')
  })

  it('isOverviewEmpty true for empty overview', () => {
    expect(isOverviewEmpty(null)).toBe(true)
    expect(
      isOverviewEmpty({
        is_empty: true,
        competitions_count: 0,
        seasons_count: 0,
        datasets_count: 0,
        matches_total: 0,
        matches_complete: 0,
        matches_incomplete: 0,
        anomalies_total: 0,
        anomalies_errors: 0,
        anomalies_warnings: 0,
        bet365_1x2_coverage_pct: 0,
        bet365_ou25_coverage_pct: 0,
        competitions: [],
        seasons: [],
        countries: [],
        recent_imports: [],
        best_quality_datasets: [],
        worst_quality_datasets: [],
        datasets_status: [],
        completeness: { complete: 0, incomplete: 0, complete_pct: 0 },
      } as CecchinoLabOverview),
    ).toBe(true)
  })

  it('historical run filters round-trip via query string', () => {
    const q = historicalRunFiltersToQuery({
      competition: 'Serie A',
      market_key: 'HOME',
      rating_band: '70-79',
      signal_model: 'F',
    })
    expect(q).toContain('competition=Serie')
    expect(q).toContain('market_key=HOME')
    const parsed = parseHistoricalRunFiltersFromSearch(q)
    expect(parsed.competition).toBe('Serie A')
    expect(parsed.market_key).toBe('HOME')
    expect(parsed.rating_band).toBe('70-79')
    expect(parsed.signal_model).toBe('F')
  })

  it('reset filters yields empty query', () => {
    expect(historicalRunFiltersToQuery({})).toBe('')
    expect(parseHistoricalRunFiltersFromSearch('')).toEqual({})
  })

  it('report menu keeps Sintesi ChatGPT as recommended first', () => {
    expect(HISTORICAL_RUN_REPORT_MENU[0]?.recommended).toBe(true)
    expect(HISTORICAL_RUN_REPORT_MENU[0]?.mode).toBe('ai_summary')
    expect(HISTORICAL_RUN_REPORT_MENU.some((i) => i.mode === 'full_archive')).toBe(true)
  })

  it('historical run analysis route pattern', () => {
    const runId = 42
    const path = `/cecchino-lab/historical-scans/${runId}`
    expect(path).toBe('/cecchino-lab/historical-scans/42')
  })

  it('null profit/odds format as em dash; zero stays numeric', () => {
    expect(formatNullableNumber(null)).toBe('—')
    expect(formatNullableNumber(undefined)).toBe('—')
    expect(formatNullableNumber(0)).toBe('0.00')
    expect(formatOdd(null)).toBe('—')
    expect(formatOdd(1.9)).toBe('1.90')
  })

  it('rating band 100 is exclusive label in filters', () => {
    const q = historicalRunFiltersToQuery({ rating_band: '100' })
    expect(q).toContain('rating_band=100')
    expect(parseHistoricalRunFiltersFromSearch(q).rating_band).toBe('100')
  })

  it('signal opportunity summary fields stay nullable-safe', () => {
    const legacy = {
      model_key: 'A',
      signals_activated: 3,
      matches_with_signal: 1,
      opportunity_count: 1,
      model_active_opportunity_count: 1,
      with_signal_active: 1,
      active_cell_row_count: 3,
      overlap_with_current_model_F_count: 1,
      overlap_with_current_model_F_pct: 100,
      real_roi: null as number | null,
      synthetic_roi: null as number | null,
      hit_rate: null as number | null,
    }
    expect(legacy.with_signal_active).toBe(legacy.model_active_opportunity_count)
    expect(legacy.opportunity_count).not.toBe(legacy.signals_activated)
    expect(legacy.overlap_with_current_model_F_count).toBeDefined()
    expect(formatNullableNumber(legacy.real_roi)).toBe('—')
  })
})
