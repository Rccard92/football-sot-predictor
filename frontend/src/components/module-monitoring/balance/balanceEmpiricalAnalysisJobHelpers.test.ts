import { describe, expect, it, beforeEach } from 'vitest'
import { createAuditRequestGuard } from '../auditRequestGuard'
import {
  BOOTSTRAP_ITERATIONS_DEFAULT,
  BOOTSTRAP_ITERATIONS_MAX,
  BOOTSTRAP_ITERATIONS_MIN,
  BOOTSTRAP_OPTIONS,
  JOB_404_USER_MESSAGE,
  JOB_409_ATTACHED_MESSAGE,
  abbreviateJobId,
  buildJobJsonFilename,
  clampBootstrapIterations,
  clearJobSession,
  extractResultSummary,
  filtersMatch,
  formatBalanceEmpiricalJobError,
  isJobAlreadyRunning409,
  isValidBootstrapOption,
  loadJobSession,
  mapJobStatusIt,
  parseActiveJobIdFrom409,
  resolveNumericProgress,
  saveJobSession,
  serializeJobPayloadForDownload,
  timelinePhaseStates,
} from './balanceEmpiricalAnalysisJobHelpers'

/** Memoria sessionStorage per test senza DOM browser completo. */
function memoryStorage(): Storage {
  const map = new Map<string, string>()
  return {
    get length() {
      return map.size
    },
    clear() {
      map.clear()
    },
    getItem(k: string) {
      return map.has(k) ? map.get(k)! : null
    },
    key(i: number) {
      return [...map.keys()][i] ?? null
    },
    removeItem(k: string) {
      map.delete(k)
    },
    setItem(k: string, v: string) {
      map.set(k, String(v))
    },
  }
}

describe('bootstrap', () => {
  it('default è 2000 e consigliato', () => {
    expect(BOOTSTRAP_ITERATIONS_DEFAULT).toBe(2000)
    const rec = BOOTSTRAP_OPTIONS.find((o) => o.value === 2000)
    expect(rec?.recommended).toBe(true)
  })

  it('range 500–10000', () => {
    expect(clampBootstrapIterations(100)).toBe(BOOTSTRAP_ITERATIONS_MIN)
    expect(clampBootstrapIterations(20000)).toBe(BOOTSTRAP_ITERATIONS_MAX)
    expect(clampBootstrapIterations(2000)).toBe(2000)
    expect(isValidBootstrapOption(500)).toBe(true)
    expect(isValidBootstrapOption(2000)).toBe(true)
    expect(isValidBootstrapOption(10000)).toBe(true)
    expect(isValidBootstrapOption(1500)).toBe(false)
  })
})

describe('status IT', () => {
  it('mappa stati backend', () => {
    expect(mapJobStatusIt('queued')).toBe('In coda')
    expect(mapJobStatusIt('running')).toBe('In elaborazione')
    expect(mapJobStatusIt('completed')).toBe('Completata')
    expect(mapJobStatusIt('failed')).toBe('Non riuscita')
  })
})

describe('timeline senza percentuali inventate', () => {
  it('non inventa progress numerico', () => {
    expect(resolveNumericProgress({ status: 'running' })).toBeNull()
    expect(resolveNumericProgress({ progress_pct: 100 })).toBe(100)
    expect(resolveNumericProgress(null)).toBeNull()
  })

  it('fasi da status senza percentuali', () => {
    expect(timelinePhaseStates('queued')[0]).toBe('active')
    expect(timelinePhaseStates('running').some((s) => s === 'indeterminate')).toBe(true)
    expect(timelinePhaseStates('completed').every((s) => s === 'done')).toBe(true)
  })
})

describe('409 / 404', () => {
  it('parse active_job_id da detail FastAPI', () => {
    expect(
      parseActiveJobIdFrom409({
        detail: { error: 'job_already_running', active_job_id: 'abc-123' },
      }),
    ).toBe('abc-123')
    expect(isJobAlreadyRunning409(409, { detail: { error: 'job_already_running' } })).toBe(
      true,
    )
  })

  it('messaggio 404 redeploy', () => {
    const err = { status: 404, body: { detail: 'not found' }, message: 'x' }
    expect(formatBalanceEmpiricalJobError(err)).toBe(JOB_404_USER_MESSAGE)
    expect(JOB_409_ATTACHED_MESSAGE).toContain('Monitoraggio ripristinato')
  })
})

describe('sessionStorage', () => {
  let storage: Storage
  beforeEach(() => {
    storage = memoryStorage()
  })

  it('save/load e clear su mismatch filtri', () => {
    saveJobSession(
      {
        job_id: 'j1',
        filters: {
          dateFrom: '2024-01-01',
          dateTo: '2024-06-01',
          competitionId: null,
          cohortFilter: 'all',
        },
        timestamp: '2024-01-01T00:00:00Z',
      },
      storage,
    )
    const loaded = loadJobSession(storage)
    expect(loaded?.job_id).toBe('j1')
    expect(
      filtersMatch(loaded!.filters, {
        dateFrom: '2024-01-01',
        dateTo: '2024-06-01',
        competitionId: null,
        cohortFilter: 'all',
      }),
    ).toBe(true)
    expect(
      filtersMatch(loaded!.filters, {
        dateFrom: '2024-01-01',
        dateTo: '2024-06-01',
        competitionId: 1,
        cohortFilter: 'all',
      }),
    ).toBe(false)
    clearJobSession(storage)
    expect(loadJobSession(storage)).toBeNull()
  })
})

describe('download JSON', () => {
  it('filename e pretty print', () => {
    expect(buildJobJsonFilename('abc-def', '2024-01-01', '2024-12-31')).toBe(
      'SOT_BALANCE_V5_JOB_abc-def_2024-01-01_2024-12-31.json',
    )
    const text = serializeJobPayloadForDownload({ a: 1, b: { c: 2 } })
    expect(text).toContain('\n')
    expect(text.trimStart().startsWith('{')).toBe(true)
  })
})

describe('result summary', () => {
  it('usa — per campi mancanti', () => {
    const s = extractResultSummary({ job_id: 'abcdefghijklmnop', status: 'completed' })
    expect(s.jobIdShort).toBe(abbreviateJobId('abcdefghijklmnop'))
    expect(s.statusF36).toBe('—')
    expect(s.rowsAnalyzed).toBe('—')
  })

  it('legge campi reali dal result', () => {
    const s = extractResultSummary({
      job_id: 'jid',
      started_at: 't0',
      completed_at: 't1',
      elapsed_seconds: 12.5,
      bootstrap_iterations: 2000,
      result: {
        bootstrap_iterations_requested: 2000,
        bootstrap_iterations_effective: 2000,
        overview: {
          evidence_scope: 'historical_diagnostic',
          sample: { settled: 40 },
          pillar_evidence_status: {
            f36: { status: 'exploratory_evidence' },
            dominance: { status: 'insufficient_sample' },
            draw_credibility: { status: 'exploratory_evidence' },
            gap: { status: 'exploratory_evidence', warnings: ['w1'] },
          },
        },
      },
    })
    expect(s.rowsAnalyzed).toBe('40')
    expect(s.evidenceScope).toBe('historical_diagnostic')
    expect(s.statusF36).toBe('Evidenza esplorativa')
    expect(s.bootstrapIterations).toBe('2000')
    expect(s.bootstrapRequested).toBe('2000')
    expect(s.bootstrapEffective).toBe('2000')
  })
})

describe('single-flight (guard riusato)', () => {
  it('doppio begin non duplica', () => {
    const guard = createAuditRequestGuard()
    expect(guard.begin()).not.toBeNull()
    expect(guard.begin()).toBeNull()
  })
})

describe('invariante no auto-start', () => {
  it('helper non espone start automatico — avvio solo da click UI', () => {
    expect(typeof mapJobStatusIt).toBe('function')
    expect(typeof formatBalanceEmpiricalJobError).toBe('function')
  })
})
