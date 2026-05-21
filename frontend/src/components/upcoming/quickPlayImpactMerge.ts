import type {
  LineupRefreshImpactPayload,
  SportApiRoundRefreshResultRow,
  UpcomingActiveMatchRow,
} from '../../lib/api'

export function impactFromRefreshRow(
  row: SportApiRoundRefreshResultRow,
): LineupRefreshImpactPayload | null {
  if (!row.direction_total) return null
  return {
    has_comparison: true,
    direction_total: row.direction_total,
    delta_total_sot: row.delta_total_sot ?? null,
    main_reason: row.main_reason ?? null,
    before_total_sot: row.before_total_sot ?? null,
    after_total_sot: row.after_total_sot ?? null,
  }
}

export function impactsFromRefreshResults(
  results: SportApiRoundRefreshResultRow[] | undefined,
): Record<number, LineupRefreshImpactPayload> {
  const out: Record<number, LineupRefreshImpactPayload> = {}
  for (const r of results ?? []) {
    const imp = impactFromRefreshRow(r)
    if (imp) out[r.fixture_id] = imp
  }
  return out
}

export function mergeMatchesWithImpacts(
  matches: UpcomingActiveMatchRow[],
  overrides: Record<number, LineupRefreshImpactPayload>,
): UpcomingActiveMatchRow[] {
  if (!Object.keys(overrides).length) return matches
  return matches.map((m) => {
    const local = overrides[m.fixture_id]
    if (!local) return m
    return { ...m, lineup_refresh_impact: local }
  })
}

export function reportUsesV20Predictions(
  matches: UpcomingActiveMatchRow[],
  modelVersion: string | null,
  v20Model: string,
): boolean {
  if (modelVersion === v20Model) return true
  return matches.some((m) => m.model_version_used === v20Model)
}
