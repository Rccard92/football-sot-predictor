import type { BetBuilderOpportunity } from '../../lib/cecchinoBetBuilderApi'
import {
  bbBadge,
  bbInEvidenzaBadge,
  bbOppTabIdle,
  bbOppTabPrimary,
  bbOppTabPrimarySelected,
  bbOppTabSelected,
} from './betBuilderStyles'
import {
  formatPurchasabilityTab,
  getPrimaryOpportunity,
  originMicroLabel,
} from './betBuilderUtils'

type Props = {
  opportunities: BetBuilderOpportunity[]
  selectedKey: string
  onSelect: (key: string) => void
  panelId: string
}

export function BetBuilderOpportunitySelector({
  opportunities,
  selectedKey,
  onSelect,
  panelId,
}: Props) {
  const primary = getPrimaryOpportunity({ opportunities })
  const primaryKey = primary?.opportunity_key
  const n = opportunities.length

  if (n === 0) return null

  if (n === 1) {
    return (
      <div className="flex flex-wrap items-center gap-2" data-testid="bet-builder-opportunity-selector">
        <span className={`${bbBadge} border-slate-200 bg-slate-50 text-slate-700`}>
          1 opportunity
        </span>
        <span className={bbInEvidenzaBadge} data-testid="in-evidenza-badge">
          In evidenza
        </span>
      </div>
    )
  }

  return (
    <div className="space-y-2" data-testid="bet-builder-opportunity-selector">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {n} opportunity
      </p>
      <div
        className="-mx-1 flex max-w-full gap-2 overflow-x-auto scroll-smooth px-1 pb-1 snap-x snap-mandatory sm:flex-wrap sm:overflow-visible sm:pb-0"
        role="tablist"
        aria-label="Seleziona opportunity"
      >
        {opportunities.map((op, index) => {
          const isPrimary = op.opportunity_key === primaryKey
          const selected = op.opportunity_key === selectedKey
          const scoreLabel = formatPurchasabilityTab(op.purchasability_v31.score)
          let className = bbOppTabIdle
          if (isPrimary && selected) className = bbOppTabPrimarySelected
          else if (isPrimary) className = bbOppTabPrimary
          else if (selected) className = bbOppTabSelected

          return (
            <button
              key={op.opportunity_key}
              type="button"
              role="tab"
              id={`bb-tab-${op.opportunity_key}`}
              aria-selected={selected}
              aria-controls={panelId}
              tabIndex={selected ? 0 : -1}
              className={`${className} ${isPrimary ? 'min-w-[5.5rem] sm:min-w-[6.5rem]' : ''}`}
              data-testid="bet-builder-opportunity-tab"
              data-opportunity-key={op.opportunity_key}
              data-primary={isPrimary ? 'true' : 'false'}
              data-market={op.market.market_key}
              data-origin={op.origin}
              onClick={() => onSelect(op.opportunity_key)}
            >
              <span className="flex w-full items-center justify-between gap-2">
                <span
                  className={`font-semibold leading-tight ${
                    isPrimary ? 'text-sm sm:text-base' : 'text-sm'
                  }`}
                >
                  {op.market.label}
                </span>
                {isPrimary && index === 0 ? (
                  <span
                    className={
                      isPrimary
                        ? 'rounded bg-white/15 px-1 py-px text-[9px] font-bold uppercase tracking-wider text-white'
                        : undefined
                    }
                    data-testid={selected || isPrimary ? 'in-evidenza-badge' : undefined}
                  >
                    In evidenza
                  </span>
                ) : null}
              </span>
              <span
                className={`tabular-nums ${
                  isPrimary ? 'text-base font-semibold text-white' : 'text-sm font-semibold text-slate-900'
                }`}
              >
                {scoreLabel}
                {scoreLabel !== 'N/D' ? (
                  <span className={isPrimary ? 'text-white/70' : 'text-slate-400'}> / 100</span>
                ) : null}
              </span>
              <span
                className={`text-[10px] font-medium ${
                  isPrimary ? 'text-white/75' : 'text-slate-500'
                }`}
              >
                {originMicroLabel(op.origin)}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
