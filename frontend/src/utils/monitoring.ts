import type { TrackedBettingPickRow } from '../lib/api'

export const LIVE_FIXTURE_STATUSES = new Set([
  'LIVE',
  '1H',
  '2H',
  'HT',
  'ET',
  'BT',
  'P',
  'INT',
])

export const LIVE_MONITOR_REFRESH_SECONDS = 300
export const LIVE_MONITOR_REFRESH_MS = LIVE_MONITOR_REFRESH_SECONDS * 1000

export function isLiveFixture(p: TrackedBettingPickRow): boolean {
  return p.status === 'live' || LIVE_FIXTURE_STATUSES.has((p.fixture_status ?? '').toUpperCase())
}

const LIVE_SOT_UNAVAILABLE_TOOLTIP =
  'API-Sports non ha restituito i tiri in porta per questo aggiornamento.'

export function formatSotDisplay(p: TrackedBettingPickRow): {
  main: string
  hint: string | null
  title: string | undefined
} {
  const main = p.sot_display ?? '—'
  const hint = p.live_hint_label ?? p.final_hint_label ?? null
  let title = p.sot_unavailable_reason ?? undefined
  if (main === 'SOT non disponibili') {
    title = LIVE_SOT_UNAVAILABLE_TOOLTIP
  }
  return { main, hint, title }
}

export function showMonitoringStatsDebug(): boolean {
  if (import.meta.env.DEV) return true
  const secret = import.meta.env.VITE_ADMIN_CRON_SECRET as string | undefined
  return Boolean(secret?.trim())
}
