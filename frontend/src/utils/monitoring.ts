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

export const LIVE_MONITOR_REFRESH_MS = 60_000

export function isLiveFixture(p: TrackedBettingPickRow): boolean {
  return p.status === 'live' || LIVE_FIXTURE_STATUSES.has((p.fixture_status ?? '').toUpperCase())
}

export function formatSotDisplay(p: TrackedBettingPickRow): {
  main: string
  hint: string | null
  title: string | undefined
} {
  const main = p.sot_display ?? '—'
  const hint = p.live_hint_label ?? p.final_hint_label ?? null
  const title = p.sot_unavailable_reason ?? undefined
  return { main, hint, title }
}
