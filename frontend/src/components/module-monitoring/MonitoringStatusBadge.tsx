import { ACCENT_CLASSES, STATUS_CLASSES, type StatusTone } from './moduleMonitoringUi'

type Props = {
  label: string
  tone?: StatusTone
  className?: string
}

export function MonitoringStatusBadge({ label, tone = 'unavailable', className = '' }: Props) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_CLASSES[tone]} ${className}`}
    >
      {label}
    </span>
  )
}

export function MonitoringAccentBadge({
  label,
  accent,
  ariaLabel,
}: {
  label: string
  accent: keyof typeof ACCENT_CLASSES
  ariaLabel?: string
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${ACCENT_CLASSES[accent].chip}`}
      aria-label={ariaLabel}
    >
      {label}
    </span>
  )
}
