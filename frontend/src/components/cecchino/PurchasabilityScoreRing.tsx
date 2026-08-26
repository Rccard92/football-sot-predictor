/**
 * Progress ring 0–100 per Indice di Acquistabilità V3.6.
 * Colore semaforico dallo score; classLabel solo da item.class persistita (mai ricalcolata).
 */

export type PurchasabilityScoreRingSize = 'sm' | 'md' | 'lg'

export type PurchasabilityScoreRingProps = {
  score: number | null | undefined
  /** Classe qualitativa già persistita (es. item.class). Non ricalcolare. */
  classLabel?: string | null
  size?: PurchasabilityScoreRingSize
  /** Label accessibile / testo accanto (default: Acquistabilità). */
  title?: string
  unavailableMessage?: string
  testId?: string
}

/** Colore stroke/tint da fasce score (allineate CLASS_THRESHOLDS backend). Non ricalcola class. */
export function scoreSemaphorePalette(score: number): {
  stroke: string
  tint: string
  track: string
} {
  if (score < 40) {
    return { stroke: '#dc2626', tint: 'rgba(220, 38, 38, 0.08)', track: '#fecaca' }
  }
  if (score < 50) {
    return { stroke: '#ea580c', tint: 'rgba(234, 88, 12, 0.08)', track: '#fed7aa' }
  }
  if (score < 60) {
    return { stroke: '#ca8a04', tint: 'rgba(202, 138, 4, 0.10)', track: '#fef08a' }
  }
  if (score < 70) {
    return { stroke: '#65a30d', tint: 'rgba(101, 163, 13, 0.10)', track: '#d9f99d' }
  }
  return { stroke: '#16a34a', tint: 'rgba(22, 163, 74, 0.10)', track: '#bbf7d0' }
}

const SIZE_MAP: Record<PurchasabilityScoreRingSize, { dim: number; stroke: number; num: string }> = {
  sm: { dim: 52, stroke: 4, num: 'text-sm' },
  md: { dim: 64, stroke: 5, num: 'text-base' },
  lg: { dim: 80, stroke: 6, num: 'text-xl' },
}

export function PurchasabilityScoreRing({
  score,
  classLabel,
  size = 'lg',
  title = 'Acquistabilità',
  unavailableMessage = 'Indice V3.6 non disponibile',
  testId = 'purchasability-score-ring',
}: PurchasabilityScoreRingProps) {
  const hasScore = score != null && !Number.isNaN(Number(score))
  const clamped = hasScore ? Math.max(0, Math.min(100, Number(score))) : 0
  const rounded = hasScore ? Math.round(Number(score)) : null
  const { dim, stroke, num } = SIZE_MAP[size]
  const r = (dim - stroke) / 2
  const c = 2 * Math.PI * r
  const offset = hasScore ? c * (1 - clamped / 100) : c
  const palette = hasScore
    ? scoreSemaphorePalette(clamped)
    : { stroke: '#94a3b8', tint: 'rgba(148, 163, 184, 0.06)', track: '#e2e8f0' }

  const aria = hasScore
    ? `${title} ${rounded} su 100${classLabel ? `, ${classLabel}` : ''}`
    : unavailableMessage

  return (
    <div
      className="flex max-w-full flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-3"
      aria-label={aria}
      data-testid={testId}
    >
      <div
        className="relative shrink-0 overflow-hidden rounded-full"
        style={{ width: dim, height: dim, backgroundColor: palette.tint }}
        role="img"
        aria-label={hasScore ? `${rounded} su 100` : 'N/D'}
      >
        <svg width={dim} height={dim} viewBox={`0 0 ${dim} ${dim}`} aria-hidden>
          <circle
            cx={dim / 2}
            cy={dim / 2}
            r={r}
            fill="none"
            stroke={palette.track}
            strokeWidth={stroke}
          />
          <circle
            cx={dim / 2}
            cy={dim / 2}
            r={r}
            fill="none"
            stroke={palette.stroke}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
            transform={`rotate(-90 ${dim / 2} ${dim / 2})`}
            style={{ transition: 'stroke-dashoffset 0.35s ease-out' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className={`font-semibold tabular-nums leading-none text-slate-900 ${num}`}
            data-testid={`${testId}-score`}
          >
            {hasScore ? rounded : 'N/D'}
          </span>
          {hasScore ? (
            <span className="text-[10px] font-medium text-slate-500">/100</span>
          ) : null}
        </div>
      </div>
      <div className="min-w-0 max-w-full space-y-0.5">
        <p className="break-words text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          {title}
        </p>
        {hasScore && classLabel ? (
          <p
            className="break-words text-sm font-semibold text-slate-800"
            data-testid={`${testId}-class`}
          >
            {classLabel}
          </p>
        ) : null}
        {!hasScore ? (
          <p className="text-sm text-slate-500" data-testid={`${testId}-unavailable`}>
            {unavailableMessage}
          </p>
        ) : null}
      </div>
    </div>
  )
}
