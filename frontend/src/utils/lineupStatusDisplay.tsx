import type { LineupStatusPayload } from '../lib/api'
import { formationBadgeClass, formationStatusTooltip } from './bettingAdviceDisplay'

export type LineupStatusLike = string | LineupStatusPayload | null | undefined

function isLineupStatusObject(status: unknown): status is LineupStatusPayload {
  return typeof status === 'object' && status != null && 'label' in status
}

/** Estrae il label testuale da lineup_status (stringa o oggetto). */
export function getLineupStatusLabel(status: unknown): string {
  if (!status) return '—'
  if (typeof status === 'string') return status
  if (isLineupStatusObject(status)) {
    return String(status.label ?? '—')
  }
  return '—'
}

/** Label display per badge formazione con logica confirmed/has_lineup. */
export function resolveFormationDisplayLabel(status: unknown): string {
  if (!status) return 'Da aggiornare'
  if (typeof status === 'string') return status || 'Da aggiornare'
  if (!isLineupStatusObject(status)) return 'Da aggiornare'

  if (status.confirmed === true) {
    return status.label || 'Ufficiale'
  }
  if (status.has_lineup === true) {
    return status.label || 'Probabili aggiornate'
  }
  return 'Da aggiornare'
}

export function FormationStatusBadge({
  status,
  className = 'inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium',
}: {
  status: unknown
  className?: string
}) {
  const label = resolveFormationDisplayLabel(status)
  const tooltip = formationStatusTooltip(label)
  return (
    <span title={tooltip || undefined} className={`${className} ${formationBadgeClass(label)}`}>
      {label}
    </span>
  )
}
