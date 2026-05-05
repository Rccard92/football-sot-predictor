import type { UpcomingMatchRow } from '../../lib/api'

export type MatchDebugLayersProps = {
  match: UpcomingMatchRow
}

export type TopPlayer = {
  name?: string
  team_name?: string
  impact_score?: number | null
  shots_on_target_per90?: number | null
  appearances?: number | null
  total_minutes?: number | null
  sample_warning?: boolean
}

