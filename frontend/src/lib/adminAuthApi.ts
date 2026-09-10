/** Sessione admin: login server-side e cookie HttpOnly.
 *
 * La password non viene mai salvata dal client: viaggia una volta nel body e
 * il browser conserva solo il cookie di sessione, che JavaScript non puo'
 * leggere. Nessun secret amministrativo finisce nel bundle.
 */

import { AdminHttpError } from './api'

function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    throw new Error(
      'VITE_API_BASE_URL non configurata. Aggiungila in .env locale o nelle variabili di build.',
    )
  }
  return String(raw).replace(/\/+$/, '')
}

export type AdminSessionState = {
  authenticated: boolean
  expires_in: number
}

async function requestAuth<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, {
    ...init,
    // Indispensabile: senza questo il cookie di sessione non viene ne' salvato
    // ne' rinviato, perche' frontend e backend stanno su domini diversi.
    credentials: 'include',
  })
  let body: unknown = null
  if ((res.headers.get('content-type') ?? '').includes('application/json')) {
    try {
      body = await res.json()
    } catch {
      body = null
    }
  }
  if (!res.ok) {
    const o = (body ?? {}) as Record<string, unknown>
    throw new AdminHttpError(
      res.status,
      typeof o.message === 'string' ? o.message : res.statusText,
      body,
    )
  }
  return body as T
}

export function getAdminSession(): Promise<AdminSessionState> {
  return requestAuth<AdminSessionState>('/api/admin/auth/session')
}

export function adminLogin(password: string): Promise<{ authenticated: boolean }> {
  return requestAuth('/api/admin/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
}

export function adminLogout(): Promise<{ authenticated: boolean }> {
  return requestAuth('/api/admin/auth/logout', { method: 'POST' })
}
