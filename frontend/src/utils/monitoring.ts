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
  let title = p.sot_unavailable_reason ?? undefined
  if (main === 'SOT non disponibili') {
    title = LIVE_SOT_UNAVAILABLE_TOOLTIP
  }
  return { main, hint: null, title }
}

export function formatSotTotal(value: number | null | undefined): string {
  if (value == null) return '—'
  return value.toFixed(2)
}

export function formatOdd(value: number | null | undefined): string {
  if (value == null) return '—'
  return value.toFixed(2)
}

export function outcomeClass(outcome: string): string {
  if (outcome === 'Vinta' || outcome === 'Vinta live') {
    return 'text-emerald-800'
  }
  if (outcome === 'Persa') {
    return 'text-rose-800'
  }
  if (outcome === 'Live') {
    return 'text-sky-800'
  }
  return 'text-slate-700'
}

/** Pillola compatta per colonna esito. */
export function outcomeBadgeClass(outcome: string): string {
  const base = 'inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold leading-tight'
  if (outcome === 'Vinta live') {
    return `${base} bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200`
  }
  if (outcome === 'Vinta') {
    return `${base} bg-emerald-100 text-emerald-900`
  }
  if (outcome === 'Persa') {
    return `${base} bg-rose-100 text-rose-900`
  }
  if (outcome === 'Live') {
    return `${base} bg-sky-100 text-sky-900`
  }
  if (outcome === 'In attesa') {
    return `${base} bg-slate-100 text-slate-700`
  }
  return `${base} bg-slate-100 text-slate-600`
}

export function showMonitoringStatsDebug(): boolean {
  if (import.meta.env.DEV) return true
  const secret = (
    (import.meta.env.VITE_CRON_SECRET as string | undefined) ||
    (import.meta.env.VITE_ADMIN_CRON_SECRET as string | undefined)
  )?.trim()
  return Boolean(secret)
}
