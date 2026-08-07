import type { BetBuilderPurchasabilityV31 } from '../../lib/cecchinoBetBuilderApi'
import { bbBadge } from './betBuilderStyles'

type Props = {
  purchasability: BetBuilderPurchasabilityV31
  size?: 'md' | 'lg'
}

export function BetBuilderPurchasabilityRing({ purchasability, size = 'lg' }: Props) {
  const score = purchasability.score
  const hasScore = score != null && !Number.isNaN(score)
  const clamped = hasScore ? Math.max(0, Math.min(100, score)) : 0
  const quality = purchasability.calculation_quality
  const dim = size === 'lg' ? 72 : 56
  const stroke = size === 'lg' ? 6 : 5
  const r = (dim - stroke) / 2
  const c = 2 * Math.PI * r
  const offset = hasScore ? c * (1 - clamped / 100) : c

  const label = hasScore
    ? `Acquistabilità V3.1 ${Math.round(score)} su 100${purchasability.class ? `, ${purchasability.class}` : ''}`
    : 'Acquistabilità V3.1 non disponibile'

  return (
    <div
      className="flex max-w-full flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-3"
      aria-label={label}
      data-testid="purchasability-ring"
    >
      <div
        className="relative shrink-0"
        style={{ width: dim, height: dim }}
        role="img"
        aria-label={hasScore ? `${Math.round(score)} su 100` : 'N/D'}
      >
        <svg width={dim} height={dim} viewBox={`0 0 ${dim} ${dim}`} aria-hidden>
          <circle
            cx={dim / 2}
            cy={dim / 2}
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth={stroke}
            className="text-slate-200"
          />
          <circle
            cx={dim / 2}
            cy={dim / 2}
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
            className={hasScore ? 'text-slate-800' : 'text-slate-300'}
            transform={`rotate(-90 ${dim / 2} ${dim / 2})`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className={`font-semibold tabular-nums leading-none text-slate-900 ${
              size === 'lg' ? 'text-lg' : 'text-sm'
            }`}
          >
            {hasScore ? Math.round(score) : 'N/D'}
          </span>
          {hasScore ? (
            <span className="text-[10px] font-medium text-slate-500">/100</span>
          ) : null}
        </div>
      </div>
      <div className="min-w-0 max-w-full space-y-1">
        <p className="break-words text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Acquistabilità
        </p>
        {purchasability.class ? (
          <p className="break-words text-sm font-semibold text-slate-800">
            {purchasability.class}
          </p>
        ) : hasScore ? null : (
          <p className="text-sm text-slate-500">Non disponibile</p>
        )}
        <div className="flex max-w-full flex-wrap gap-1">
          {quality === 'provisional' ? (
            <span
              className={`${bbBadge} max-w-full self-start whitespace-normal border-amber-200 bg-amber-50 text-amber-900`}
            >
              Provvisoria
            </span>
          ) : quality === 'full' ? (
            <span
              className={`${bbBadge} max-w-full self-start whitespace-normal border-slate-200 bg-white text-slate-700`}
            >
              Completa
            </span>
          ) : null}
        </div>
      </div>
    </div>
  )
}
