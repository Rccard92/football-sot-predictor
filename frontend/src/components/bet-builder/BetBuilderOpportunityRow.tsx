import type { BetBuilderOpportunity } from '../../lib/cecchinoBetBuilderApi'
import { BetBuilderContextBlock } from './BetBuilderContextBlock'
import { BetBuilderPriceBlock } from './BetBuilderPriceBlock'
import { BetBuilderPurchasabilityBlock } from './BetBuilderPurchasabilityBlock'
import { BetBuilderSignalsBlock } from './BetBuilderSignalsBlock'
import { bbBadge } from './betBuilderStyles'
import { originBadgeLabel } from './betBuilderUtils'

type Props = {
  opportunity: BetBuilderOpportunity
}

function originBadgeClass(origin: BetBuilderOpportunity['origin']): string {
  if (origin === 'price') return `${bbBadge} border-sky-200 bg-sky-50 text-sky-900`
  if (origin === 'signals') return `${bbBadge} border-violet-200 bg-violet-50 text-violet-900`
  return `${bbBadge} border-emerald-200 bg-emerald-50 text-emerald-900`
}

export function BetBuilderOpportunityRow({ opportunity }: Props) {
  return (
    <div
      className="space-y-3 border-t border-slate-100 pt-3 first:border-t-0 first:pt-0"
      data-testid="bet-builder-opportunity-row"
      data-origin={opportunity.origin}
      data-market={opportunity.market.market_key}
      data-opportunity-key={opportunity.opportunity_key}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1.5">
          <p className="text-lg font-semibold tracking-tight text-slate-900">
            {opportunity.market.label}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {opportunity.origin === 'price_and_signals' ? (
              <>
                <span className={`${bbBadge} border-sky-200 bg-sky-50 text-sky-900`}>QUOTA</span>
                <span className={`${bbBadge} border-violet-200 bg-violet-50 text-violet-900`}>
                  SEGNALI
                </span>
              </>
            ) : (
              <span className={originBadgeClass(opportunity.origin)}>
                {originBadgeLabel(opportunity.origin)}
              </span>
            )}
          </div>
        </div>
        <BetBuilderPurchasabilityBlock
          purchasability={opportunity.purchasability_v31}
          compact
        />
      </div>

      <BetBuilderPriceBlock price={opportunity.price_value} compact />
      <BetBuilderSignalsBlock
        signals={opportunity.signals}
        marketKey={opportunity.market.market_key}
        compact
      />
      <BetBuilderContextBlock
        context={opportunity.context_support}
        marketLabel={opportunity.market.label}
        compact
      />
    </div>
  )
}
