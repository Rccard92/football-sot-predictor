import type { BetBuilderPurchasabilityV36 } from '../../lib/cecchinoBetBuilderApi'
import { BetBuilderPurchasabilityRing } from './BetBuilderPurchasabilityRing'

type Props = {
  purchasability: BetBuilderPurchasabilityV36
  compact?: boolean
}

/** Wrapper compatibile: ring V3.6 al posto della progress bar. */
export function BetBuilderPurchasabilityBlock({ purchasability, compact = false }: Props) {
  return (
    <div data-testid={compact ? 'purchasability-compact' : 'purchasability-block'}>
      <BetBuilderPurchasabilityRing
        purchasability={purchasability}
        size={compact ? 'md' : 'lg'}
      />
    </div>
  )
}
