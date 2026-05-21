export type SportApiFreshnessLevel = 'aggiornato' | 'da_verificare' | 'vecchio'

export type SportApiFreshnessBadge = {
  level: SportApiFreshnessLevel
  label: string
}

const FRESHNESS_STYLES: Record<SportApiFreshnessLevel, string> = {
  aggiornato: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  da_verificare: 'border-amber-200 bg-amber-50 text-amber-950',
  vecchio: 'border-rose-200 bg-rose-50 text-rose-900',
}

export function freshnessBadgeClass(level: SportApiFreshnessLevel): string {
  return FRESHNESS_STYLES[level]
}

/** Kickoff report: 22-05-2026 18:00 (Europe/Rome). */
export function formatKickoffReport(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const parts = d.toLocaleString('it-IT', {
    timeZone: 'Europe/Rome',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  return parts.replace(',', '').replace(/\//g, '-')
}

/** Formato leggibile: 21-05-2026 14:37 (Europe/Rome). */
export function formatSportApiFetchedAt(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('it-IT', {
    timeZone: 'Europe/Rome',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function hoursUntilKickoff(kickoffAt: string | null | undefined): number | null {
  if (!kickoffAt) return null
  const k = new Date(kickoffAt).getTime()
  if (Number.isNaN(k)) return null
  return (k - Date.now()) / 3600000
}

function ageHours(fetchedAt: string): number | null {
  const t = new Date(fetchedAt).getTime()
  if (Number.isNaN(t)) return null
  return (Date.now() - t) / 3600000
}

/** Badge informativo vicino all’ultimo aggiornamento (non blocca azioni). */
export function getSportApiFreshnessBadge(
  fetchedAt: string | null | undefined,
  kickoffAt?: string | null,
): SportApiFreshnessBadge | null {
  if (!fetchedAt) return null
  const ageH = ageHours(fetchedAt)
  if (ageH == null) return null

  const untilKick = hoursUntilKickoff(kickoffAt)
  const within48h = untilKick != null && untilKick > 0 && untilKick <= 48

  if (!within48h) {
    return { level: 'aggiornato', label: 'Aggiornato' }
  }
  if (ageH > 6) return { level: 'vecchio', label: 'Vecchio' }
  if (ageH > 2) return { level: 'da_verificare', label: 'Da verificare' }
  return { level: 'aggiornato', label: 'Aggiornato' }
}
