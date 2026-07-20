import { describe, expect, it } from 'vitest'
import {
  AUDIT_TIMEOUT_USER_MESSAGE,
  createAuditRequestGuard,
  isAuditTimeoutError,
} from './auditRequestGuard'
import { ANALYSIS_PACKS_AUDIT_TIMEOUT_MS } from '../../lib/cecchinoModuleMonitoringApi'

describe('createAuditRequestGuard', () => {
  it('single-flight: secondo begin ritorna null mentre in flight', () => {
    const guard = createAuditRequestGuard()
    const first = guard.begin()
    expect(first).not.toBeNull()
    expect(guard.begin()).toBeNull()
    guard.end(first!.requestId)
    expect(guard.begin()).not.toBeNull()
  })

  it('generation id: risposta vecchia non è current dopo abort', () => {
    const guard = createAuditRequestGuard()
    const first = guard.begin()!
    guard.abort()
    expect(guard.isCurrent(first.requestId)).toBe(false)
    expect(guard.isInFlight()).toBe(false)
  })

  it('end di requestId non corrente non sblocca un altro flight', () => {
    const guard = createAuditRequestGuard()
    const first = guard.begin()!
    guard.abort()
    const second = guard.begin()!
    guard.end(first.requestId)
    expect(guard.isInFlight()).toBe(true)
    guard.end(second.requestId)
    expect(guard.isInFlight()).toBe(false)
  })
})

describe('isAuditTimeoutError', () => {
  it('riconosce timeout e abort', () => {
    expect(isAuditTimeoutError(new Error('Timeout operazione dopo 240 s'))).toBe(true)
    expect(isAuditTimeoutError(new Error('The operation was aborted'))).toBe(true)
    expect(isAuditTimeoutError(new Error('network failed'))).toBe(false)
  })
})

describe('ANALYSIS_PACKS_AUDIT_TIMEOUT_MS', () => {
  it('usa 240 secondi dedicati', () => {
    expect(ANALYSIS_PACKS_AUDIT_TIMEOUT_MS).toBe(240_000)
    expect(AUDIT_TIMEOUT_USER_MESSAGE).toContain('tempo del previsto')
  })
})
