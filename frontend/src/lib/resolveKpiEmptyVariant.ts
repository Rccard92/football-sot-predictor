import type { KpiSignalsSummaryResponse } from './cecchinoKpiSignalsApi'

export type KpiEmptyVariant = 'no_fixtures' | 'not_synced' | 'no_rating'

/**
 * Decide empty-state per Segnali KPI.
 * Le activations del summary hanno precedenza assoluta sui diagnostics
 * (assenti di proposito quando include_diagnostics=false e activations > 0).
 */
export function resolveKpiEmptyVariant(
  summary: KpiSignalsSummaryResponse | null | undefined,
): KpiEmptyVariant | null {
  if (!summary) return null

  const activations = summary.overall.activations ?? 0
  if (activations > 0) return null

  const diag = summary.diagnostics
  if (!diag) return null

  if ((diag.today_fixtures_count ?? 0) === 0) return 'no_fixtures'
  if ((diag.kpi_signals_created ?? 0) === 0 && (diag.fixtures_with_kpi_panel ?? 0) > 0) {
    return 'not_synced'
  }
  if ((diag.kpi_rows_below_50 ?? 0) > 0) return 'no_rating'
  return 'not_synced'
}
