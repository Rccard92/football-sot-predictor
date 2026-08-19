import type {
  CecchinoPurchasabilityV35CandidateKey,
  CecchinoPurchasabilityV35Item,
} from '../../lib/cecchinoTodayApi'
import { bbOppTabIdle, bbOppTabScroll, bbOppTabSelected } from '../bet-builder/betBuilderStyles'
import {
  formatV35IntegerScore,
  getV35CandidateClass,
  getV35CandidateScore,
  getV35MarketLabel,
  v35BadgeClass,
} from './cecchinoPurchasabilityV35UiUtils'

type Props = {
  items: CecchinoPurchasabilityV35Item[]
  selectedMarketKey: string
  selectedCandidate: CecchinoPurchasabilityV35CandidateKey
  onSelect: (marketKey: string) => void
  panelId: string
}

export function CecchinoPurchasabilityV35MarketSelector({
  items,
  selectedMarketKey,
  selectedCandidate,
  onSelect,
  panelId,
}: Props) {
  return (
    <div className="space-y-2" data-testid="v35-market-selector">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Mercati attivi</p>
      <div
        className={`${bbOppTabScroll} gap-2`}
        role="tablist"
        aria-label="Mercati V3.5"
        id={`${panelId}-v35-market-panel`}
      >
        {items.map((item) => {
          const selected = selectedMarketKey === item.market_key
          const score = getV35CandidateScore(item, selectedCandidate)
          const classLabel = getV35CandidateClass(item, selectedCandidate)
          return (
            <button
              key={item.market_key}
              type="button"
              role="tab"
              id={`${panelId}-v35-market-${item.market_key}`}
              aria-selected={selected}
              aria-controls={`${panelId}-v35-detail`}
              data-testid={`v35-selector-${item.market_key}`}
              data-selected={selected ? 'true' : 'false'}
              data-score={score ?? undefined}
              className={selected ? bbOppTabSelected : bbOppTabIdle}
              onClick={() => onSelect(item.market_key)}
            >
              <span className="flex flex-col items-start gap-0.5 text-left">
                <span className="text-[11px] font-medium">{getV35MarketLabel(item)}</span>
                <span className="flex items-center gap-1.5">
                  <span className="text-sm font-bold tabular-nums">{formatV35IntegerScore(score)}</span>
                  {classLabel ? (
                    <span
                      className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-semibold ring-1 ${v35BadgeClass(classLabel)}`}
                    >
                      {classLabel}
                    </span>
                  ) : null}
                </span>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
