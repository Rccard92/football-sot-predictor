import type { V36Item } from '../../lib/cecchinoTodayApi'
import { bbOppTabIdle, bbOppTabScroll, bbOppTabSelected } from '../bet-builder/betBuilderStyles'
import {
  formatV36FinalScore,
  getV36MarketLabel,
  getV36Score,
} from './cecchinoPurchasabilityV36UiUtils'

type Props = {
  items: V36Item[]
  selectedMarketKey: string
  onSelect: (marketKey: string) => void
  panelId: string
}

export function CecchinoPurchasabilityV36MarketSelector({
  items,
  selectedMarketKey,
  onSelect,
  panelId,
}: Props) {
  return (
    <div className="space-y-2" data-testid="v36-market-selector">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Mercati valutati</p>
      <div
        className={`${bbOppTabScroll} gap-2`}
        role="tablist"
        aria-label="Mercati V3.6"
        id={`${panelId}-v36-market-panel`}
      >
        {items.map((item) => {
          const selected = selectedMarketKey === item.market_key
          const score = getV36Score(item)
          const quote = item.input?.execution_quote
          return (
            <button
              key={item.market_key}
              type="button"
              role="tab"
              id={`${panelId}-v36-market-${item.market_key}`}
              aria-selected={selected}
              aria-controls={`${panelId}-v36-detail`}
              data-testid={`v36-selector-${item.market_key}`}
              data-selected={selected ? 'true' : 'false'}
              data-raw-score={item.raw_score ?? undefined}
              className={selected ? bbOppTabSelected : bbOppTabIdle}
              onClick={() => onSelect(item.market_key)}
            >
              <span className="flex flex-col items-start gap-0.5 text-left">
                <span className="text-[11px] font-medium">{getV36MarketLabel(item)}</span>
                <span className="text-sm font-bold tabular-nums">{formatV36FinalScore(score)}</span>
                <span className="text-[10px] tabular-nums text-slate-500">
                  quota {quote != null ? Number(quote).toFixed(2) : 'N/D'}
                </span>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
