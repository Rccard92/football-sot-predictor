import type { BetBuilderPurchasabilityV36 } from '../../lib/cecchinoBetBuilderApi'
import { PurchasabilityScoreRing } from '../cecchino/PurchasabilityScoreRing'

type Props = {
  purchasability: BetBuilderPurchasabilityV36
  size?: 'md' | 'lg'
}

/** Ring Acquistabilità display — sempre V3.6 (nessun fallback V3.1/V3.5). */
export function BetBuilderPurchasabilityRing({ purchasability, size = 'lg' }: Props) {
  const available = purchasability.available === true
  const score = available ? purchasability.score : null

  return (
    <PurchasabilityScoreRing
      score={score}
      classLabel={available ? purchasability.class ?? null : null}
      size={size}
      title="Acquistabilità V3.6"
      unavailableMessage="Indice V3.6 non disponibile"
      testId="purchasability-ring"
    />
  )
}
