type Props = { title: string; error: string; onRetry?: () => void }

export function HistoricalRunSectionError({ title, error, onRetry }: Props) {
  return (
    <div
      className="rounded-xl border p-4"
      style={{ borderColor: 'rgba(240,113,120,0.35)', background: 'rgba(240,113,120,0.08)' }}
    >
      <h4 className="font-semibold text-[var(--lab-err)]">{title}</h4>
      <p className="mt-1 text-sm text-[var(--lab-muted)]">{error}</p>
      {onRetry ? (
        <button type="button" className="lab-btn mt-3 text-sm" onClick={onRetry}>
          Riprova
        </button>
      ) : null}
    </div>
  )
}
