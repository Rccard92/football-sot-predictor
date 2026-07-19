import { AdminHttpError, adminGetJson } from './api'

export type MonitoringModuleKeyApi =
  | 'purchasability'
  | 'balance-v5'
  | 'goal-intensity-v5'
  | 'signals'

export type ModuleOverviewItem = {
  module_key: MonitoringModuleKeyApi | string
  status?: string | null
  version?: string | null
  coverage?: number | null
  fixtures?: number | null
  settled?: number | null
  last_snapshot_at?: string | null
  next_review_at?: string | null
  warnings?: string[]
  eligible_fixtures?: number | null
  covered_fixtures?: number | null
  settled_covered_fixtures?: number | null
  coverage_numerator?: number | null
  coverage_denominator?: number | null
  activations?: number | null
}

export type ModuleMonitoringOverview = {
  generated_at: string
  modules: ModuleOverviewItem[]
}

export type ModuleMonitoringFilters = {
  date_from: string
  date_to: string
  competition_id?: number
  market_key?: string
  include_rows?: boolean
  include_debug?: boolean
}

const BASE = '/api/cecchino/module-monitoring'

function qs(filters: ModuleMonitoringFilters): string {
  const p = new URLSearchParams()
  p.set('date_from', filters.date_from)
  p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.market_key) p.set('market_key', filters.market_key)
  if (filters.include_rows != null) p.set('include_rows', String(filters.include_rows))
  if (filters.include_debug != null) p.set('include_debug', String(filters.include_debug))
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
    throw new AdminHttpError(res.status, message, null)
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

export async function getModuleMonitoringOverview(
  filters: Pick<ModuleMonitoringFilters, 'date_from' | 'date_to' | 'competition_id'>,
): Promise<ModuleMonitoringOverview> {
  const p = new URLSearchParams()
  p.set('date_from', filters.date_from)
  p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  return adminGetJson(`${BASE}/overview?${p.toString()}`)
}

export async function downloadModuleAnalysisPack(
  moduleKey: MonitoringModuleKeyApi,
  filters: ModuleMonitoringFilters,
): Promise<void> {
  await downloadBlob(
    `${BASE}/${moduleKey}/analysis-pack.zip${qs(filters)}`,
    `SOT_MONITOR_${moduleKey}_${filters.date_from}_${filters.date_to}.zip`,
  )
}

export async function downloadModuleSummaryJson(
  moduleKey: MonitoringModuleKeyApi,
  filters: ModuleMonitoringFilters,
): Promise<void> {
  await downloadBlob(
    `${BASE}/${moduleKey}/summary.json${qs({ ...filters, include_rows: false })}`,
    `SOT_MONITOR_${moduleKey}_summary.json`,
  )
}

export async function downloadModuleRowsCsv(
  moduleKey: MonitoringModuleKeyApi,
  filters: ModuleMonitoringFilters,
): Promise<void> {
  await downloadBlob(
    `${BASE}/${moduleKey}/rows.csv${qs({ ...filters, include_rows: true })}`,
    `SOT_MONITOR_${moduleKey}_${filters.date_from}_${filters.date_to}_rows.csv`,
  )
}
