type Props = {
  message: string
  onRetry?: () => void
}

export function HistoricalKpiEmptyState({ message, onRetry }: Props) {
  return (
    <div
      className="rounded-xl border p-6 text-center"
      style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
    >
      <p className="text-sm text-[var(--lab-muted)]">{message}</p>
      {onRetry ? (
        <button type="button" className="lab-btn mt-4 text-sm" onClick={onRetry}>
          Riprova
        </button>
      ) : null}
    </div>
  )
}
