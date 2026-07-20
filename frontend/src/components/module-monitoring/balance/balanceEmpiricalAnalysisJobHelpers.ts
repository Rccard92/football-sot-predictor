/**
 * Helper puri per il launcher job analisi statistica Balance v5 Step 2B.
 * Nessuna chiamata API qui — solo mapping, persistenza e download locale.
 */

export const BALANCE_ANALYSIS_JOB_STORAGE_KEY = 'cecchino_balance_v5_analysis_job_v1'

export const BOOTSTRAP_ITERATIONS_MIN = 500
export const BOOTSTRAP_ITERATIONS_MAX = 10000
export const BOOTSTRAP_ITERATIONS_DEFAULT = 2000
export const DEFAULT_POLL_AFTER_MS = 2000

export const BOOTSTRAP_OPTIONS = [
  { value: 500, label: '500 — verifica rapida' },
  { value: 2000, label: '2000 — analisi standard', recommended: true },
  { value: 5000, label: '5000 — analisi approfondita' },
  { value: 10000, label: '10000 — analisi massima' },
] as const

export type BalanceJobStatus = 'queued' | 'running' | 'completed' | 'failed'

export type BalanceJobFiltersSnapshot = {
  dateFrom: string
  dateTo: string
  competitionId: number | null
  cohortFilter: string
}

export type BalanceJobSessionRecord = {
  job_id: string
  filters: BalanceJobFiltersSnapshot
  timestamp: string
  poll_after_ms?: number
  bootstrap_iterations?: number
}

export const TIMELINE_PHASES = [
  'Preparazione dataset',
  'Analisi quattro pilastri',
  'Bootstrap e intervalli',
  'Stabilità e dependency',
  'Generazione risultato',
] as const

export type TimelinePhaseState = 'pending' | 'active' | 'done' | 'indeterminate'

export function clampBootstrapIterations(raw: unknown): number {
  const n = typeof raw === 'number' ? raw : Number(raw)
  if (!Number.isFinite(n)) return BOOTSTRAP_ITERATIONS_DEFAULT
  return Math.min(
    BOOTSTRAP_ITERATIONS_MAX,
    Math.max(BOOTSTRAP_ITERATIONS_MIN, Math.round(n)),
  )
}

export function isValidBootstrapOption(n: number): boolean {
  return (
    Number.isInteger(n) &&
    n >= BOOTSTRAP_ITERATIONS_MIN &&
    n <= BOOTSTRAP_ITERATIONS_MAX &&
    (BOOTSTRAP_OPTIONS as readonly { value: number }[]).some((o) => o.value === n)
  )
}

export function mapJobStatusIt(status: string | null | undefined): string {
  switch (status) {
    case 'queued':
      return 'In coda'
    case 'running':
      return 'In elaborazione'
    case 'completed':
      return 'Completata'
    case 'failed':
      return 'Non riuscita'
    default:
      return status && String(status).trim() ? String(status) : '—'
  }
}

/** Nessuna percentuale inventata: solo stati da status/current_stage. */
export function timelinePhaseStates(
  status: string | null | undefined,
): TimelinePhaseState[] {
  const s = String(status || '')
  if (s === 'completed') {
    return TIMELINE_PHASES.map(() => 'done')
  }
  if (s === 'failed') {
    return ['done', 'done', 'indeterminate', 'pending', 'pending']
  }
  if (s === 'queued') {
    return ['active', 'pending', 'pending', 'pending', 'pending']
  }
  if (s === 'running') {
    return ['done', 'indeterminate', 'indeterminate', 'indeterminate', 'pending']
  }
  return TIMELINE_PHASES.map(() => 'pending')
}

/** Progresso numerico: mai inventato — null se backend non lo fornisce. */
export function resolveNumericProgress(payload: Record<string, unknown> | null): number | null {
  if (!payload) return null
  const candidates = [payload.progress_pct, payload.progress_percent, payload.progress]
  for (const c of candidates) {
    if (typeof c === 'number' && Number.isFinite(c) && c >= 0 && c <= 100) {
      return c
    }
  }
  return null
}

export function abbreviateJobId(jobId: string | null | undefined, keep = 8): string {
  if (!jobId) return '—'
  const s = String(jobId)
  if (s.length <= keep + 4) return s
  return `${s.slice(0, keep)}…`
}

export function filtersMatch(
  a: BalanceJobFiltersSnapshot,
  b: BalanceJobFiltersSnapshot,
): boolean {
  return (
    a.dateFrom === b.dateFrom &&
    a.dateTo === b.dateTo &&
    (a.competitionId ?? null) === (b.competitionId ?? null) &&
    (a.cohortFilter || 'all') === (b.cohortFilter || 'all')
  )
}

export function loadJobSession(
  storage: Storage | null = typeof sessionStorage !== 'undefined' ? sessionStorage : null,
): BalanceJobSessionRecord | null {
  if (!storage) return null
  try {
    const raw = storage.getItem(BALANCE_ANALYSIS_JOB_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as BalanceJobSessionRecord
    if (!parsed || typeof parsed.job_id !== 'string' || !parsed.filters) return null
    return parsed
  } catch {
    return null
  }
}

export function saveJobSession(
  record: BalanceJobSessionRecord,
  storage: Storage | null = typeof sessionStorage !== 'undefined' ? sessionStorage : null,
): void {
  if (!storage) return
  storage.setItem(BALANCE_ANALYSIS_JOB_STORAGE_KEY, JSON.stringify(record))
}

export function clearJobSession(
  storage: Storage | null = typeof sessionStorage !== 'undefined' ? sessionStorage : null,
): void {
  if (!storage) return
  storage.removeItem(BALANCE_ANALYSIS_JOB_STORAGE_KEY)
}

/**
 * Estrae active_job_id da AdminHttpError body (FastAPI: { detail: { error, active_job_id } }).
 */
export function parseActiveJobIdFrom409(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null
  const o = body as Record<string, unknown>
  if (typeof o.active_job_id === 'string' && o.active_job_id) return o.active_job_id
  if (typeof o.error === 'string' && o.error === 'job_already_running') {
    /* fall through to detail */
  }
  const detail = o.detail
  if (detail && typeof detail === 'object') {
    const d = detail as Record<string, unknown>
    if (typeof d.active_job_id === 'string' && d.active_job_id) return d.active_job_id
  }
  return null
}

export function isJobAlreadyRunning409(status: number, body: unknown): boolean {
  if (status !== 409) return false
  if (!body || typeof body !== 'object') return false
  const o = body as Record<string, unknown>
  if (o.error === 'job_already_running') return true
  const detail = o.detail
  if (detail && typeof detail === 'object') {
    return (detail as Record<string, unknown>).error === 'job_already_running'
  }
  return parseActiveJobIdFrom409(body) != null
}

export const JOB_404_USER_MESSAGE =
  'Il risultato temporaneo non è più disponibile, probabilmente a seguito di un redeploy. Avvia una nuova analisi.'

export const JOB_409_ATTACHED_MESSAGE =
  'È già presente un’analisi in corso. Monitoraggio ripristinato.'

export function formatBalanceEmpiricalJobError(err: unknown): string {
  if (err && typeof err === 'object' && 'status' in err) {
    const status = Number((err as { status: number }).status)
    const body = (err as { body?: unknown }).body
    if (status === 404) return JOB_404_USER_MESSAGE
    if (isJobAlreadyRunning409(status, body)) return JOB_409_ATTACHED_MESSAGE
    if (status === 400) {
      const msg =
        err instanceof Error ? err.message : 'Parametri non validi per l’analisi.'
      return msg.includes('Richiesta') || msg.length < 3
        ? 'Parametri non validi (date, coorte o iterazioni bootstrap). Controlla i filtri.'
        : msg
    }
    if (status >= 500) {
      return 'Errore interno del server durante l’analisi. Riprova tra poco.'
    }
    if (err instanceof Error && err.message) return err.message
  }
  if (err instanceof Error) {
    const lower = err.message.toLowerCase()
    if (lower.includes('timeout') || lower.includes('aborted')) {
      return 'Timeout durante l’analisi. Puoi riprovare o riprendere il monitoraggio se il job è ancora attivo.'
    }
    if (
      lower.includes('failed to fetch') ||
      lower.includes('network') ||
      lower.includes('offline')
    ) {
      return 'Connessione interrotta. Verifica la rete e riprova.'
    }
    return err.message
  }
  return 'Operazione non riuscita.'
}

export function buildJobJsonFilename(
  jobId: string,
  dateFrom: string,
  dateTo: string,
): string {
  const safeId = String(jobId).replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 36) || 'unknown'
  const df = String(dateFrom).slice(0, 10)
  const dt = String(dateTo).slice(0, 10)
  return `SOT_BALANCE_V5_JOB_${safeId}_${df}_${dt}.json`
}

/** Pretty-print JSON UTF-8 senza alterare valori (JSON.stringify gestisce NaN→null solo se già nel payload). */
export function serializeJobPayloadForDownload(payload: unknown): string {
  return `${JSON.stringify(payload, null, 2)}\n`
}

export function downloadJobResultJson(
  payload: unknown,
  filename: string,
  doc: Document = typeof document !== 'undefined' ? document : (null as unknown as Document),
): void {
  const text = serializeJobPayloadForDownload(payload)
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  try {
    const a = doc.createElement('a')
    a.href = url
    a.download = filename
    a.rel = 'noopener'
    doc.body.appendChild(a)
    a.click()
    a.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}

export type ResultSummaryFields = {
  jobIdShort: string
  startedAt: string
  completedAt: string
  duration: string
  rowsAnalyzed: string
  bootstrapIterations: string
  evidenceScope: string
  statusF36: string
  statusDominance: string
  statusCredibilityX: string
  statusGap: string
  warningCount: string
}

function dash(v: unknown): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'number' && Number.isNaN(v)) return '—'
  return String(v)
}

function pillarStatus(
  result: Record<string, unknown> | null,
  key: string,
): string {
  if (!result) return '—'
  const pes = result.pillar_evidence_status
  if (!pes || typeof pes !== 'object') {
    const overview = result.overview
    if (overview && typeof overview === 'object') {
      const op = (overview as Record<string, unknown>).pillar_evidence_status
      if (op && typeof op === 'object') {
        const p = (op as Record<string, unknown>)[key]
        if (p && typeof p === 'object') {
          return dash((p as Record<string, unknown>).status)
        }
      }
    }
    return '—'
  }
  const p = (pes as Record<string, unknown>)[key]
  if (p && typeof p === 'object') {
    return dash((p as Record<string, unknown>).status)
  }
  return '—'
}

function countWarnings(result: Record<string, unknown> | null): string {
  if (!result) return '—'
  let n = 0
  let found = false
  const visit = (node: unknown) => {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) {
      for (const x of node) visit(x)
      return
    }
    const o = node as Record<string, unknown>
    if (Array.isArray(o.warnings)) {
      found = true
      n += o.warnings.length
    }
    for (const v of Object.values(o)) {
      if (v && typeof v === 'object') visit(v)
    }
  }
  visit(result)
  return found ? String(n) : '—'
}

export function extractResultSummary(
  job: Record<string, unknown> | null,
): ResultSummaryFields {
  const result =
    job && job.result && typeof job.result === 'object'
      ? (job.result as Record<string, unknown>)
      : null
  const overview =
    result && result.overview && typeof result.overview === 'object'
      ? (result.overview as Record<string, unknown>)
      : result
  const sample =
    overview && overview.sample && typeof overview.sample === 'object'
      ? (overview.sample as Record<string, unknown>)
      : null
  const rows =
    sample?.settled ??
    sample?.rows_total ??
    sample?.rows_analyzed ??
    (result as { sample_size?: unknown } | null)?.sample_size

  const elapsed = job?.elapsed_seconds
  let duration = '—'
  if (typeof elapsed === 'number' && Number.isFinite(elapsed)) {
    duration = `${elapsed} s`
  }

  return {
    jobIdShort: abbreviateJobId(
      typeof job?.job_id === 'string' ? job.job_id : null,
    ),
    startedAt: dash(job?.started_at ?? job?.created_at),
    completedAt: dash(job?.completed_at),
    duration,
    rowsAnalyzed: dash(rows),
    bootstrapIterations: dash(
      job?.bootstrap_iterations ?? result?.bootstrap_iterations,
    ),
    evidenceScope: dash(
      overview?.evidence_scope ?? result?.evidence_scope,
    ),
    statusF36: pillarStatus(overview ?? result, 'f36'),
    statusDominance: pillarStatus(overview ?? result, 'dominance'),
    statusCredibilityX: pillarStatus(overview ?? result, 'draw_credibility'),
    statusGap: pillarStatus(overview ?? result, 'gap'),
    warningCount: countWarnings(result),
  }
}

export function formatElapsedClock(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  if (m <= 0) return `${s} s`
  return `${m} min ${s} s`
}
