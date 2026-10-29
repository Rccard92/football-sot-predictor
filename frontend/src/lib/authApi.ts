/** Account utenti (dal 29/10/2026): login con email, sessione nel cookie HttpOnly, gestione utenti.
 *
 * La password non viene mai salvata dal client: viaggia una volta nel body. La password generata per un
 * nuovo utente arriva solo nella risposta della creazione (o del reset) e va mostrata una volta sola.
 */

import { AdminHttpError } from './api'

function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    throw new Error('VITE_API_BASE_URL non configurata. Aggiungila in .env locale o nelle variabili di build.')
  }
  return String(raw).replace(/\/+$/, '')
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, { ...init, credentials: 'include' })
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
    const message =
      typeof o.message === 'string' ? o.message : typeof o.detail === 'string' ? o.detail : res.statusText
    throw new AdminHttpError(res.status, message, body)
  }
  return body as T
}

function json(method: string, payload?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  }
}

export type UserRole = 'admin' | 'user'

export type AppUser = {
  id: number
  email: string
  first_name: string
  last_name: string
  phone: string | null
  role: UserRole
  tabs: string[]
  must_change_password: boolean
  is_active: boolean
  last_login_at: string | null
  password_changed_at: string | null
  created_at: string | null
  active_devices?: number
  last_seen_at?: string | null
}

export type AuthMe = {
  enforced: boolean
  authenticated: boolean
  kind?: 'user' | 'emergency_admin' | 'audit'
  is_admin?: boolean
  tabs?: string[]
  allowed_tabs?: string[]
  must_change_password?: boolean
  user?: AppUser | null
}

export type TabInfo = { key: string; label: string; path: string; group: string }

export function getMe(): Promise<AuthMe> {
  return request<AuthMe>('/api/auth/me')
}

export function login(email: string, password: string): Promise<{ authenticated: boolean }> {
  return request('/api/auth/login', json('POST', { email, password }))
}

export function logout(): Promise<{ authenticated: boolean }> {
  return request('/api/auth/logout', { method: 'POST' })
}

export function changePassword(currentPassword: string, newPassword: string): Promise<AuthMe> {
  return request<AuthMe>(
    '/api/auth/change-password',
    json('POST', { current_password: currentPassword, new_password: newPassword }),
  )
}

// --- gestione utenti (solo amministratori) -------------------------------------------------------

export type UserInput = {
  first_name: string
  last_name: string
  email: string
  phone: string
  role: UserRole
  tabs: string[]
}

export type UserSession = {
  id: number
  created_at: string
  last_seen_at: string
  expires_at: string
  active: boolean
  revoked_at: string | null
  revoke_reason: string | null
  ip: string | null
  user_agent: string | null
}

export type LoginEvent = {
  id: number
  user_id: number | null
  email: string | null
  success: boolean
  reason: string | null
  ip: string | null
  user_agent: string | null
  created_at: string
}

export function listTabs(): Promise<{ tabs: TabInfo[] }> {
  return request('/api/admin/users/tabs')
}

export function listUsers(): Promise<{ users: AppUser[] }> {
  return request('/api/admin/users')
}

export function createUser(input: UserInput): Promise<{ user: AppUser; password: string }> {
  return request('/api/admin/users', json('POST', input))
}

export function updateUser(id: number, input: Partial<UserInput>): Promise<{ user: AppUser }> {
  return request(`/api/admin/users/${id}`, json('PATCH', input))
}

export function resetUserPassword(id: number): Promise<{ user: AppUser; password: string }> {
  return request(`/api/admin/users/${id}/reset-password`, { method: 'POST' })
}

export function deactivateUser(id: number): Promise<{ user: AppUser }> {
  return request(`/api/admin/users/${id}/deactivate`, { method: 'POST' })
}

export function activateUser(id: number): Promise<{ user: AppUser }> {
  return request(`/api/admin/users/${id}/activate`, { method: 'POST' })
}

export function revokeUserSessions(id: number): Promise<{ user: AppUser; revoked: number }> {
  return request(`/api/admin/users/${id}/revoke-sessions`, { method: 'POST' })
}

export function listUserSessions(id: number): Promise<{ sessions: UserSession[] }> {
  return request(`/api/admin/users/${id}/sessions`)
}

export function listLoginEvents(userId?: number): Promise<{ failed_last_24h: number; events: LoginEvent[] }> {
  const q = userId === undefined ? '' : `?user_id=${userId}`
  return request(`/api/admin/users/login-events${q}`)
}
