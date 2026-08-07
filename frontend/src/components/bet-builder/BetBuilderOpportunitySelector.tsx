import type { BetBuilderOpportunity } from '../../lib/cecchinoBetBuilderApi'
import {
  bbBadge,
  bbInEvidenzaBadge,
  bbInEvidenzaBadgeOnDark,
  bbInEvidenzaBadgeOnLight,
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

          const onDark = isPrimary && selected
          const labelClass = onDark
            ? 'text-sm font-semibold leading-tight text-white sm:text-base'
            : isPrimary
              ? 'text-sm font-semibold leading-tight text-emerald-950 sm:text-base'
              : selected
                ? 'text-sm font-semibold leading-tight text-slate-950'
                : 'text-sm font-semibold leading-tight text-slate-800'
          const scoreClass = onDark
            ? 'tabular-nums text-base font-semibold text-white'
            : isPrimary
              ? 'tabular-nums text-base font-semibold text-emerald-950'
              : 'tabular-nums text-sm font-semibold text-slate-900'
          const mutedClass = onDark
            ? 'text-white/70'
            : isPrimary
              ? 'text-emerald-700/70'
              : 'text-slate-400'
          const originClass = onDark
            ? 'text-[10px] font-medium text-white/75'
            : isPrimary
              ? 'text-[10px] font-medium text-emerald-800/80'
              : 'text-[10px] font-medium text-slate-500'

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
              data-selected={selected ? 'true' : 'false'}
              data-market={op.market.market_key}
              data-origin={op.origin}
              onClick={() => onSelect(op.opportunity_key)}
            >
              <span className="flex w-full items-center justify-between gap-2">
                <span className={labelClass}>{op.market.label}</span>
                {isPrimary && index === 0 ? (
                  <span
                    className={onDark ? bbInEvidenzaBadgeOnDark : bbInEvidenzaBadgeOnLight}
                    data-testid="in-evidenza-badge"
                  >
                    In evidenza
                  </span>
                ) : null}
              </span>
              <span className={scoreClass}>
                {scoreLabel}
                {scoreLabel !== 'N/D' ? (
                  <span className={mutedClass}> / 100</span>
                ) : null}
              </span>
              <span className={originClass}>{originMicroLabel(op.origin)}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
