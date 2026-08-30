import { describe, expect, it } from 'vitest'
import type {
  KpiSignalsBucket,
  KpiSignalsDiagnosticsPayload,
  KpiSignalsSummaryResponse,
} from './cecchinoKpiSignalsApi'
import { resolveKpiEmptyVariant } from './resolveKpiEmptyVariant'

const emptyBucket = (activations: number): KpiSignalsBucket => ({
  activations,
  settled: 0,
  won: 0,
  lost: 0,
  pending: 0,
  win_rate: null,
  avg_book_odds_all: null,
  avg_book_odds_won: null,
  quota_void: null,
  profit_units: null,
  roi_pct: null,
})

function makeSummary(
  activations: number,
  diagnostics?: KpiSignalsDiagnosticsPayload,
): KpiSignalsSummaryResponse {
  return {
    status: 'ok',
    filters: {},
    overall: emptyBucket(activations),
    by_rating_bucket: [],
    by_selection: [],
    heatmap: { rows: [], columns: [], cells: [] },
    top: { best_profit: [], best_roi: [], worst_profit: [] },
    diagnostics,
  }
}

function makeDiag(
  partial: Partial<KpiSignalsDiagnosticsPayload>,
): KpiSignalsDiagnosticsPayload {
  return {
    today_fixtures_count: 0,
    fixtures_with_kpi_panel: 0,
    kpi_rows_seen: 0,
    kpi_signals_created: 0,
    kpi_rows_below_50: 0,
    kpi_rows_without_book_odds: 0,
    ...partial,
  }
}

describe('resolveKpiEmptyVariant', () => {
  it('returns null when summary is missing', () => {
    expect(resolveKpiEmptyVariant(null)).toBeNull()
    expect(resolveKpiEmptyVariant(undefined)).toBeNull()
  })

  it('CASO A critico: activations > 0 e diagnostics undefined → null (mostra dati)', () => {
    const summary = makeSummary(100, undefined)
    expect(summary.diagnostics).toBeUndefined()
    expect(resolveKpiEmptyVariant(summary)).toBeNull()
  })

  it('CASO B: activations = 0 e today_fixtures_count = 0 → no_fixtures', () => {
    expect(
      resolveKpiEmptyVariant(
        makeSummary(
          0,
          makeDiag({
            today_fixtures_count: 0,
            fixtures_with_kpi_panel: 0,
            kpi_signals_created: 0,
          }),
        ),
      ),
    ).toBe('no_fixtures')
  })

  it('CASO C: activations = 0, panel > 0, signals_created = 0 → not_synced', () => {
    expect(
      resolveKpiEmptyVariant(
        makeSummary(
          0,
          makeDiag({
            today_fixtures_count: 10,
            fixtures_with_kpi_panel: 5,
            kpi_signals_created: 0,
            kpi_rows_below_50: 3,
          }),
        ),
      ),
    ).toBe('not_synced')
  })

  it('CASO D: activations = 0, fixtures > 0, signals_created > 0, below_50 > 0 → no_rating', () => {
    expect(
      resolveKpiEmptyVariant(
        makeSummary(
          0,
          makeDiag({
            today_fixtures_count: 12,
            fixtures_with_kpi_panel: 8,
            kpi_signals_created: 4,
            kpi_rows_below_50: 20,
          }),
        ),
      ),
    ).toBe('no_rating')
  })

  it('CASO E: activations = 0 e diagnostics assenti → null (non no_fixtures)', () => {
    expect(resolveKpiEmptyVariant(makeSummary(0, undefined))).toBeNull()
  })
})
