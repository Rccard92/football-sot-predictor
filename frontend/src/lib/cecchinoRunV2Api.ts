/** Client API Cecchino RUN V2 — namespace separato dalla Scansione storica V1. */

import { AdminHttpError } from './api'

export const RUN_V2_CONFIRM_TOKEN = 'RUN_CECCHINO_RUN_V2'

export const RUN_V2_EXPORT_FILES = [
  'FULL.csv',
  'core_markets_long.csv',
  'run_summary.json',
  'SOURCE_RAW.csv',
  'DATA_DICTIONARY.json',
] as const

export type RunV2ExportFile = (typeof RUN_V2_EXPORT_FILES)[number]

function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    throw new Error(
      'VITE_API_BASE_URL non configurata. Aggiungila in .env locale o nelle variabili di build.',
    )
  }
  return String(raw).replace(/\/+$/, '')
}

export type CecchinoRunV2Competition = {
  competition: string
  season_label: string
  matches: number
  eligible_core?: number
  target_eligible_per_competition?: number
  target_reached?: boolean
  eligible_vs_target?: string
  first_kickoff: string | null
  last_kickoff: string | null
}

export type CecchinoRunV2MarketCoverage = {
  market_key: string
  export_key: string
  observation_layer: string
  rows: number
  rows_with_quote: number
  rows_with_prediction: number
  quote_coverage_pct: number | null
  used_for_prediction: boolean
  pre_match_input_safe: boolean
}

export type CecchinoRunV2Summary = {
  run_id?: number
  run_version?: string
  export_schema_version?: string
  feature_contract_version?: string
  quote_policy_version?: string
  core_formula_freeze?: boolean
  matches?: number
  date_range?: { start: string | null; end: string | null }
  competitions?: CecchinoRunV2Competition[]
  market_coverage?: CecchinoRunV2MarketCoverage[]
  extra_stats_coverage?: {
    snapshots?: number
    with_referee?: number
    with_prior_history?: number
    referee_coverage_pct?: number | null
  }
  economic_benchmark?: Record<string, unknown>
  leakage_audit?: Record<string, unknown> | null
  [key: string]: unknown
}

export type CecchinoRunV2 = {
  run_id: number
  run_version: string
  /** Stato persistito sul DB. */
  status: string
  /** Stato operativo: `interrupted` se la run non ha piu un worker attivo. */
  effective_status: string
  is_stale: boolean
  worker_alive: boolean
  can_resume: boolean
  can_cancel: boolean
  heartbeat_at: string | null
  heartbeat_age_seconds: number | null
  stale_heartbeat_seconds: number
  run_scope: string
  /** Stagione Lab nello scope della RUN (da module_policy_json). */
  season_label: string | null
  max_matches: number | null
  requested_at: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
  updated_at: string | null
  matches_total: number
  matches_processed: number
  matches_error: number
  market_rows_written: number
  leakage_violations: number
  progress_pct: number | null
  min_kickoff_at: string | null
  max_kickoff_at: string | null
  current_competition: string | null
  last_processed_kickoff_at: string | null
  cancel_requested: boolean
  quote_policy: Record<string, unknown> | null
  module_policy: Record<string, unknown> | null
  coverage: Record<string, unknown> | null
  summary: CecchinoRunV2Summary | null
  leakage_audit: Record<string, unknown> | null
  warnings: unknown[] | null
  error: Record<string, unknown> | null
  source_git_commit: string | null
  source_git_commit_source: string | null
  source_revision_status: string | null
}

export type CecchinoRunV2Preflight = {
  season_label: string
  status: 'ready' | 'blocked' | string
  matches_total: number
  competitions_count: number
  competitions: string[]
  datasets_count: number
  date_range: { start: string | null; end: string | null }
  blocking_anomalies: Array<{ code?: string; message?: string }>
  warnings: Array<{ code?: string; message?: string }>
}

export type CecchinoRunV2ExportManifest = {
  run_id: number
  run_version: string
  files: Record<string, string>
  counts: Record<string, number>
}

/** Errore API RUN V2 che preserva il codice e i dettagli del backend. */
export class RunV2ApiError extends AdminHttpError {
  readonly code: string
  readonly details: Record<string, unknown>
  constructor(status: number, message: string, code: string, details: Record<string, unknown>) {
    super(status, message, { error: code, details })
    this.name = 'RunV2ApiError'
    this.code = code
    this.details = details
  }
}

async function parseRunV2Body(res: Response): Promise<Record<string, unknown>> {
  if (!(res.headers.get('content-type') ?? '').includes('application/json')) {
    return {}
  }
  try {
    return ((await res.json()) ?? {}) as Record<string, unknown>
  } catch {
    return {}
  }
}

function raiseIfRunV2Error(res: Response, body: Record<string, unknown>): void {
  if (!res.ok || body.status === 'error') {
    const detail = typeof body.detail === 'string' ? body.detail : null
    throw new RunV2ApiError(
      res.status,
      typeof body.message === 'string' ? body.message : detail || res.statusText,
      typeof body.error === 'string' ? body.error : 'run_v2_error',
      (body.details as Record<string, unknown>) ?? {},
    )
  }
}

async function getRunV2Json<T>(path: string): Promise<T> {
  const base = getApiBase()
  const res = await fetch(`${base}${path}`, {
    method: 'GET',
    // List/detail/preflight sono pubblici (metadata). Export/manifest e i
    // POST admin richiedono il cookie di sessione.
    credentials: 'include',
  })
  const body = await parseRunV2Body(res)
  raiseIfRunV2Error(res, body)
  return body as T
}

async function postRunV2<T>(path: string, payload?: unknown): Promise<T> {
  const base = getApiBase()
  const res = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
    // Il control plane richiede la sessione admin: senza il cookie il backend
    // risponde 401 e la UI apre il login.
    credentials: 'include',
  })
  const body = await parseRunV2Body(res)
  raiseIfRunV2Error(res, body)
  return body as T
}

export function listRunsV2(): Promise<CecchinoRunV2[]> {
  return getRunV2Json<{ items: CecchinoRunV2[] }>('/api/cecchino-run-v2').then(
    (r) => r.items ?? [],
  )
}

export function getRunV2(runId: number): Promise<CecchinoRunV2> {
  return getRunV2Json(`/api/cecchino-run-v2/${runId}`)
}

export function preflightRunV2(season: string): Promise<CecchinoRunV2Preflight> {
  const q = new URLSearchParams({ season })
  return getRunV2Json(`/api/cecchino-run-v2/preflight?${q.toString()}`)
}

export function startRunV2(options: {
  season: string
  maxMatches?: number | null
  pilotStrategy?: 'max_matches' | 'eligible_per_competition' | null
  eligiblePerCompetition?: number | null
}): Promise<CecchinoRunV2> {
  const body: Record<string, unknown> = {
    confirm: RUN_V2_CONFIRM_TOKEN,
    season: options.season,
  }
  if (options.maxMatches != null) body.max_matches = options.maxMatches
  if (options.pilotStrategy) body.pilot_strategy = options.pilotStrategy
  if (options.eligiblePerCompetition != null) {
    body.eligible_per_competition = options.eligiblePerCompetition
  }
  return postRunV2('/api/admin/cecchino-run-v2', body)
}

export function resumeRunV2(runId: number): Promise<CecchinoRunV2> {
  return postRunV2(`/api/admin/cecchino-run-v2/${runId}/resume`)
}

export function cancelRunV2(runId: number): Promise<CecchinoRunV2> {
  return postRunV2(`/api/admin/cecchino-run-v2/${runId}/cancel`)
}

export function getRunV2ExportManifest(runId: number): Promise<CecchinoRunV2ExportManifest> {
  return getRunV2Json(`/api/cecchino-run-v2/${runId}/export/manifest`)
}

/** Scarica un artefatto rigenerato dal DB al momento della richiesta. */
export async function downloadRunV2Export(
  runId: number,
  file: RunV2ExportFile = 'FULL.csv',
): Promise<void> {
  const base = getApiBase()
  const params = new URLSearchParams({ file })
  const res = await fetch(`${base}/api/cecchino-run-v2/${runId}/export?${params.toString()}`, {
    credentials: 'include',
  })
  if (!res.ok) {
    let message = `Export RUN V2 fallito (${res.status})`
    try {
      const body = (await res.json()) as { detail?: string; message?: string }
      message = body?.detail || body?.message || message
    } catch {
      /* ignore */
    }
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="?([^"]+)"?/i.exec(cd)
  const filename = match?.[1] || `cecchino_run_v2_${runId}_${file}`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Pacchetto AI ZIP lossless (admin login on click come gli altri export). */
export async function downloadRunV2AiBundle(runId: number): Promise<void> {
  const base = getApiBase()
  const res = await fetch(`${base}/api/cecchino-run-v2/${runId}/export/ai-bundle`, {
    credentials: 'include',
  })
  if (!res.ok) {
    let message = `Export AI bundle RUN V2 fallito (${res.status})`
    try {
      const body = (await res.json()) as { detail?: string; message?: string }
      message = body?.detail || body?.message || message
    } catch {
      /* ignore */
    }
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="?([^"]+)"?/i.exec(cd)
  const filename = match?.[1] || `CECCHINO_RUN_V2_RUN_${runId}_AI_BUNDLE.zip`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

const RUN_V2_STATUS_LABELS: Record<string, string> = {
  pending: 'In attesa',
  running: 'In corso',
  interrupted: 'Interrotta — riprendibile',
  completed: 'Completata',
  completed_with_warnings: 'Completata con avvisi',
  failed: 'Fallita',
  cancelled: 'Annullata',
}

export function runV2StatusLabel(status: string | null | undefined): string {
  if (!status) return '—'
  return RUN_V2_STATUS_LABELS[status] ?? status
}

/** Solo gli stati con un worker che sta effettivamente avanzando: guida il polling. */
export function isRunV2Active(run: Pick<CecchinoRunV2, 'effective_status'>): boolean {
  return run.effective_status === 'pending' || run.effective_status === 'running'
}

export function isRunV2Completed(run: Pick<CecchinoRunV2, 'status'>): boolean {
  return run.status === 'completed' || run.status === 'completed_with_warnings'
}

export function runV2ScopeLabel(
  run: Pick<CecchinoRunV2, 'run_scope' | 'max_matches' | 'season_label' | 'module_policy'>,
): string {
  const season = run.season_label ? ` · ${run.season_label}` : ''
  if (run.run_scope === 'balanced_pilot') {
    const epc =
      (run.module_policy?.eligible_per_competition as number | undefined) ??
      (run.module_policy?.target_eligible_per_competition as number | undefined) ??
      3
    return `Pilota maturo — ${epc} eleggibili/comp${season}`
  }
  if (run.run_scope === 'pilot') {
    return `Pilota${run.max_matches ? ` — ${run.max_matches} match` : ''}${season}`
  }
  return `Completa${season}`
}

export function formatRunV2Date(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })
}
