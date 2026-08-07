import type {
  BetBuilderBalanceContextPayload,
  BetBuilderContextSupport,
  BetBuilderGoalIntensityContextPayload,
} from '../../lib/cecchinoBetBuilderApi'
import { BetBuilderBalanceContext } from './BetBuilderBalanceContext'
import { BetBuilderGoalIntensityContext } from './BetBuilderGoalIntensityContext'

type Props = {
  context: BetBuilderContextSupport
  marketLabel: string
}

function isBalancePayload(
  payload: BetBuilderContextSupport['payload'],
): payload is BetBuilderBalanceContextPayload {
  return Boolean(payload && 'pillars' in payload)
}

function isGiPayload(
  payload: BetBuilderContextSupport['payload'],
): payload is BetBuilderGoalIntensityContextPayload {
  return Boolean(
    payload &&
      ('expected_total_goals' in payload ||
        'probability_selection' in payload ||
        'official' in payload),
  )
}

export function BetBuilderContextBlock({ context, marketLabel }: Props) {
  if (
    !context.available &&
    context.reason === 'no_validated_context_module'
  ) {
    return (
      <p className="text-xs text-slate-500" data-testid="context-unavailable">
        Supporto contestuale specialistico non disponibile
      </p>
    )
  }

  if (!context.available) {
    return (
      <p className="text-xs text-slate-500" data-testid="context-unavailable-generic">
        Supporto contestuale non disponibile
      </p>
    )
  }

  if (context.module === 'balance_v5' && isBalancePayload(context.payload)) {
    return <BetBuilderBalanceContext payload={context.payload} />
  }

  if (context.module === 'goal_intensity_v5' && isGiPayload(context.payload)) {
    return (
      <BetBuilderGoalIntensityContext payload={context.payload} marketLabel={marketLabel} />
    )
  }

  return null
}
