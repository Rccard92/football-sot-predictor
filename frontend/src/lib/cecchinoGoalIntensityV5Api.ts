/**
 * Client API per Goal Intensity v5 - Module Monitoring
 * Endpoint canonici sotto /api/cecchino/module-monitoring/goal-intensity-v5/
 */

import { adminGetJson } from './api'

const BASE = '/api/cecchino/module-monitoring/goal-intensity-v5'

export type GoalIntensityV5Overview = {
  status?: string
  version?: string
  global_snapshots?: number
  snapshots_in_period?: number
  prospective_snapshots?: number
  completed_snapshots?: number
  pending_snapshots?: number
  minimum_sample?: number
  snapshot_collection_progress?: number
  completed_results_progress?: number
  first_effective_date?: string
  last_effective_date?: string
  warnings?: string[]
  [key: string]: unknown
}

export type GoalIntensityV5Dimensions = {
  status?: string
  version?: string
  snapshot_count?: number
  dimensions?: Array<{
    key: string
    label: string
    components?: Array<{
      key: string
      label: string
      description?: string
    }>
  }> | Record<string, unknown>
  dimensions_list?: Array<{
    key?: string
    label?: string
    components?: Array<{
      key?: string
      label?: string
      description?: string
    }>
  }>
  warnings?: string[]
  [key: string]: unknown
}

export type GoalIntensityV5Candidates = {
  status?: string
  version?: string
  candidates?: Array<{
    id?: string
    candidate_id?: string
    role: string
    description?: string
    formula?: string
    active?: boolean
  }>
  warnings?: string[]
  [key: string]: unknown
}

export type GoalIntensityV5ProspectiveResults = {
  status?: string
  version?: string
  snapshots_count?: number
  completed_count?: number
  pending_count?: number
  collection_progress?: number
  completed_progress?: number
  warnings?: string[]
  [key: string]: unknown
}

export type GoalIntensityV5Calibration = {
  status?: string
  version?: string
  calibration_status?: string
  candidates_calibrated?: number
  sample_size?: number
  calibration_quality?: string
  warnings?: string[]
  [key: string]: unknown
}

export type GoalIntensityV5Stability = {
  status?: string
  version?: string
  stability_status?: string
  temporal_consistency?: number | null
  cross_fold_consistency?: number | null
  warnings?: string[]
  [key: string]: unknown
}

export type GoalIntensityV5Readiness = {
  status?: string
  version?: string
  operational_status?: string
  scientific_maturity?: string
  scientific_maturity_label_it?: string
  recommended_next_step?: string
  recommended_next_step_label_it?: string
  signals_integration_status?: string
  current_decision?: string
  prospective_progress?: {
    completed?: number
    pending?: number
    snapshots?: number
    minimum?: number
    progress_pct?: number
    remaining?: number
    excess?: number
    minimum_reached?: boolean
    [key: string]: unknown
  }
  monitoring_normalized?: Record<string, unknown>
  phase_2b_benchmark?: Record<string, unknown>
  readiness_gates?: Array<{
    key: string
    label: string
    status: string
    value?: unknown
    threshold?: unknown
  }>
  warnings?: string[]
  [key: string]: unknown
}

export type GoalIntensityV5Benchmark = {
  status?: string
  version?: string
  v4_version?: string
  v5_bundle_version?: string
  definition_hash?: string
  cohort?: Record<string, unknown>
  continuous_total_goals?: {
    metrics_by_model?: Record<string, Record<string, unknown>>
    comparisons?: Array<Record<string, unknown>>
  }
  goals_ge_2?: {
    metrics_by_model?: Record<string, Record<string, unknown>>
    comparisons?: Array<Record<string, unknown>>
  }
  goals_ge_3?: {
    metrics_by_model?: Record<string, Record<string, unknown>>
    comparisons?: Array<Record<string, unknown>>
  }
  btts?: Record<string, unknown>
  scientific_interpretation?: Record<string, unknown>
  quality_checks?: Record<string, unknown>
  warnings?: string[]
  [key: string]: unknown
}

export type GoalIntensityV5DataHealth = {
  status?: string
  version?: string
  data_quality_status?: string
  coverage?: number | null
  completeness?: number | null
  warnings?: string[]
  [key: string]: unknown
}

export type GoalIntensityV5ExportStatus = {
  status?: string
  version?: string
  files_expected?: string[]
  files_available?: string[]
  rows?: number | null
  completeness?: string
  export_completeness_status?: string
  blocking_reasons?: string[]
  estimated_size_bytes?: number | null
  warnings?: string[]
  [key: string]: unknown
}

export type GoalIntensityV5Filters = {
  date_from: string
  date_to: string
  competition_id?: number | null
  source_cohort?: string
}

function qs(filters: GoalIntensityV5Filters): string {
  const p = new URLSearchParams()
  p.set('date_from', filters.date_from)
  p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.source_cohort && filters.source_cohort !== 'all') {
    p.set('source_cohort', filters.source_cohort)
  }
  return `?${p.toString()}`
}

function apiBase(): string {
  return (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
}

async function downloadBlob(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`${apiBase()}${path}`)
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json()
      message = body?.detail || body?.message || message
    } catch {
      /* ignore */
    }
    throw new Error(message)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="?([^"]+)"?/i.exec(cd)
  const filename = match?.[1] || fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export async function getGoalIntensityV5Overview(
  filters: GoalIntensityV5Filters,
  opts?: { signal?: AbortSignal },
): Promise<GoalIntensityV5Overview> {
  return adminGetJson(`${BASE}/overview${qs(filters)}`, opts)
}

export async function getGoalIntensityV5Dimensions(
  filters: GoalIntensityV5Filters,
  opts?: { signal?: AbortSignal },
): Promise<GoalIntensityV5Dimensions> {
  return adminGetJson(`${BASE}/dimensions${qs(filters)}`, opts)
}

export async function getGoalIntensityV5Candidates(
  filters: GoalIntensityV5Filters,
  opts?: { signal?: AbortSignal },
): Promise<GoalIntensityV5Candidates> {
  return adminGetJson(`${BASE}/candidates${qs(filters)}`, opts)
}

export async function getGoalIntensityV5ProspectiveResults(
  filters: GoalIntensityV5Filters,
  opts?: { signal?: AbortSignal },
): Promise<GoalIntensityV5ProspectiveResults> {
  return adminGetJson(`${BASE}/prospective-results${qs(filters)}`, opts)
}

export async function getGoalIntensityV5Calibration(
  filters: GoalIntensityV5Filters,
  opts?: { signal?: AbortSignal },
): Promise<GoalIntensityV5Calibration> {
  return adminGetJson(`${BASE}/calibration${qs(filters)}`, opts)
}

export async function getGoalIntensityV5Stability(
  filters: GoalIntensityV5Filters,
  opts?: { signal?: AbortSignal },
): Promise<GoalIntensityV5Stability> {
  return adminGetJson(`${BASE}/stability${qs(filters)}`, opts)
}

export async function getGoalIntensityV5Readiness(
  filters: GoalIntensityV5Filters,
  opts?: { signal?: AbortSignal },
): Promise<GoalIntensityV5Readiness> {
  return adminGetJson(`${BASE}/readiness${qs(filters)}`, opts)
}

export async function getGoalIntensityV5Benchmark(
  filters: GoalIntensityV5Filters,
  opts?: { signal?: AbortSignal },
): Promise<GoalIntensityV5Benchmark> {
  return adminGetJson(`${BASE}/benchmark-v4-v5${qs(filters)}`, opts)
}

export async function getGoalIntensityV5DataHealth(
  filters: GoalIntensityV5Filters,
  opts?: { signal?: AbortSignal },
): Promise<GoalIntensityV5DataHealth> {
  return adminGetJson(`${BASE}/data-health${qs(filters)}`, opts)
}

export async function getGoalIntensityV5ExportStatus(
  filters: GoalIntensityV5Filters,
  opts?: { signal?: AbortSignal },
): Promise<GoalIntensityV5ExportStatus> {
  return adminGetJson(`${BASE}/export-status${qs(filters)}`, opts)
}

export async function downloadGoalIntensityV5AnalysisPack(
  filters: GoalIntensityV5Filters,
): Promise<void> {
  await downloadBlob(
    `${BASE}/analysis-pack.zip${qs(filters)}`,
    `SOT_MONITOR_goal-intensity-v5_${filters.date_from}_${filters.date_to}.zip`,
  )
}

export async function downloadGoalIntensityV5ReadinessDossier(
  filters: GoalIntensityV5Filters,
): Promise<void> {
  await downloadBlob(
    `${BASE}/export${qs(filters)}`,
    `SOT_GOAL_INTENSITY_V5_READINESS_${filters.date_from}_${filters.date_to}.zip`,
  )
}
