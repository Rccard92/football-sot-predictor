import type {
  SportApiCompetitionLineupsIngestSummary,
  SportApiCompetitionLineupsResultRow,
  SportApiRoundRefreshResultRow,
  SportApiRoundRefreshSummary,
} from '../../lib/api'

export type RefreshSummary = SportApiRoundRefreshSummary | SportApiCompetitionLineupsIngestSummary

export type RefreshResultRow = SportApiRoundRefreshResultRow | SportApiCompetitionLineupsResultRow

export function isRoundRefreshSummary(
  summary: RefreshSummary | null | undefined,
): summary is SportApiRoundRefreshSummary {
  return !!summary && 'updated' in summary && 'total_fixtures' in summary
}

export function isCompetitionLineupsSummary(
  summary: RefreshSummary | null | undefined,
): summary is SportApiCompetitionLineupsIngestSummary {
  return !!summary && 'fixtures_checked' in summary && 'lineups_imported' in summary
}

export function isRoundRefreshRow(row: RefreshResultRow): row is SportApiRoundRefreshResultRow {
  return 'direction_total' in row || 'delta_total_sot' in row || 'match_name' in row
}

export function getRowMatchName(row: RefreshResultRow): string {
  if (isRoundRefreshRow(row) && row.match_name) return row.match_name
  if ('match_api_sports' in row && row.match_api_sports) return row.match_api_sports
  return `Fixture ${row.fixture_id ?? '—'}`
}

export function getRowDirection(row: RefreshResultRow): string | null | undefined {
  return isRoundRefreshRow(row) ? row.direction_total : null
}

export function getRowDelta(row: RefreshResultRow): number | null | undefined {
  return isRoundRefreshRow(row) ? row.delta_total_sot : null
}

export function getRowReason(row: RefreshResultRow): string {
  if (isRoundRefreshRow(row)) return row.main_reason ?? ''
  if ('reason' in row && row.reason) return row.reason
  return ''
}
