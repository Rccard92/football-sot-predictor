import type { BetBuilderPurchasabilityV31 } from '../../lib/cecchinoBetBuilderApi'
import { BetBuilderPurchasabilityRing } from './BetBuilderPurchasabilityRing'

type Props = {
  purchasability: BetBuilderPurchasabilityV31
  compact?: boolean
}

/** Wrapper compatibile: ring al posto della progress bar. */
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
