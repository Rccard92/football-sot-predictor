import type { BetBuilderOpportunity } from '../../../lib/cecchinoBetBuilderApi'
import { bbPrimaryBtn, bbSecondaryBtn } from '../betBuilderStyles'
import type { BetBuilderCartCtaState } from './betBuilderCartUtils'

type Props = {
  opportunity: BetBuilderOpportunity
  cta: BetBuilderCartCtaState
  onAdd: () => void
  onReplace: () => void
  onRemove: () => void
  /** Desktop top-right vs mobile full-width. */
  layout: 'desktop' | 'mobile'
}

export function BetBuilderCartAddButton({
  opportunity,
  cta,
  onAdd,
  onReplace,
  onRemove,
  layout,
}: Props) {
  const widthClass = layout === 'mobile' ? 'w-full' : 'w-auto max-w-full'
  const bookHint = cta.bookOddsMissing ? (
    <p
      className="mt-1 text-[11px] text-amber-800"
      data-testid="bet-builder-cart-odds-missing-hint"
    >
      Quota Book non disponibile
    </p>
  ) : null

  if (cta.kind === 'added') {
    return (
      <div
        className={layout === 'mobile' ? 'w-full' : 'hidden sm:block'}
        data-testid="bet-builder-cart-slot"
        data-cta="added"
      >
        <div className={`flex flex-wrap items-center gap-2 ${widthClass}`}>
          <span
            className={`${bbSecondaryBtn} pointer-events-none border-emerald-300 bg-emerald-50 text-emerald-950`}
            aria-label={cta.ariaLabel}
            data-testid="bet-builder-cart-added-badge"
          >
            {cta.label}
          </span>
          <button
            type="button"
            className={bbSecondaryBtn}
            onClick={onRemove}
            aria-label={`Rimuovi ${opportunity.market.label} dalla schedina`}
            data-testid="bet-builder-cart-remove-cta"
          >
            Rimuovi
          </button>
        </div>
        {bookHint}
      </div>
    )
  }

  if (cta.kind === 'replace') {
    return (
      <div
        className={layout === 'mobile' ? 'w-full' : 'hidden sm:block'}
        data-testid="bet-builder-cart-slot"
        data-cta="replace"
      >
        <button
          type="button"
          className={`${bbPrimaryBtn} ${widthClass} text-left leading-snug`}
          onClick={onReplace}
          aria-label={cta.ariaLabel}
          data-testid="bet-builder-cart-replace-cta"
        >
          {cta.label}
        </button>
        {bookHint}
      </div>
    )
  }

  return (
    <div
      className={layout === 'mobile' ? 'w-full' : 'hidden sm:block'}
      data-testid="bet-builder-cart-slot"
      data-cta="add"
    >
      <button
        type="button"
        className={`${bbPrimaryBtn} ${widthClass}`}
        onClick={onAdd}
        aria-label={cta.ariaLabel}
        data-testid="bet-builder-cart-add-cta"
      >
        {cta.label}
      </button>
      {bookHint}
    </div>
  )
}
