/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN_AUTH_REQUIRED_EVENT, installAdminFetchInterceptor, isAdminAuthFailure } from './adminAuthEvents'

describe('accesso amministratore (20/10/2026)', () => {
  afterEach(() => vi.restoreAllMocks())

  it('riconosce i 401 dell’area admin', () => {
    expect(isAdminAuthFailure(401, 'https://b/api/admin/cecchino/today/scan-day/start')).toBe(true)
    expect(isAdminAuthFailure(401, 'https://b/api/x', 'Sessione admin assente o scaduta')).toBe(true)
    expect(isAdminAuthFailure(403, 'https://b/api/admin/x')).toBe(false)
    expect(isAdminAuthFailure(401, 'https://b/api/cecchino/today')).toBe(false)
  })

  it('il backend riceve il cookie e un 401 admin apre il login; gli altri domini restano intatti', async () => {
    const calls: { url: string; init?: RequestInit }[] = []
    const fake = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push({ url, init })
      return new Response('{}', { status: url.includes('/api/admin/') ? 401 : 200 })
    })
    window.fetch = fake as unknown as typeof window.fetch
    const opened = vi.fn()
    window.addEventListener(ADMIN_AUTH_REQUIRED_EVENT, opened)
    installAdminFetchInterceptor('https://backend.test')

    await window.fetch('https://backend.test/api/cecchino/today', { method: 'GET' })
    await window.fetch('https://backend.test/api/admin/cecchino/today/update-results', { method: 'POST' })
    await window.fetch('https://altro.test/x')

    expect(calls[0].init?.credentials).toBe('include')
    expect(calls[1].init?.method).toBe('POST')
    expect(calls[2].init?.credentials).toBeUndefined()
    expect(opened).toHaveBeenCalledTimes(1)
  })
})
