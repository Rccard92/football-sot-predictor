import type { CecchinoPurchasabilityV31Item } from '../../lib/cecchinoTodayApi'
import {
  bbOppTabIdle,
  bbOppTabScroll,
  bbOppTabSelected,
} from '../bet-builder/betBuilderStyles'
import {
  getMarketDisplayLabel,
  getPurchasabilityClassLabel,
  getPurchasabilityScore,
} from './cecchinoPurchasabilityUiUtils'

type Props = {
  items: CecchinoPurchasabilityV31Item[]
  selectedMarketKey: string
  onSelect: (marketKey: string) => void
  panelId: string
}

export function CecchinoPurchasabilitySelector({
  items,
  selectedMarketKey,
  onSelect,
  panelId,
}: Props) {
  if (items.length === 0) return null

  return (
    <div
      className={bbOppTabScroll}
      role="tablist"
      aria-label="Seleziona mercato Acquistabilità"
      data-testid="cecchino-purchasability-selector"
    >
      {items.map((item) => {
        const selected = item.market_key === selectedMarketKey
        const score = getPurchasabilityScore(item)
        const classLabel = getPurchasabilityClassLabel(item)
        const label = getMarketDisplayLabel(item)
        const className = selected ? bbOppTabSelected : bbOppTabIdle

        return (
          <button
            key={item.market_key}
            type="button"
            role="tab"
            id={`${panelId}-tab-${item.market_key}`}
            aria-selected={selected}
            aria-controls={`${panelId}-panel-${item.market_key}`}
            className={className}
            data-testid={`purch-selector-${item.market_key}`}
            data-selected={selected ? 'true' : 'false'}
            onClick={() => onSelect(item.market_key)}
          >
            <span className="text-sm font-semibold leading-tight text-slate-900">{label}</span>
            <span className="tabular-nums text-base font-semibold text-slate-900">{score}</span>
            {classLabel ? (
              <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
                {classLabel.replace(' provvisoria', '')}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}
