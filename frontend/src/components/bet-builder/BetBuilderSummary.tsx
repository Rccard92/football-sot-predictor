import type { BetBuilderOpportunitiesSummary } from '../../lib/cecchinoBetBuilderApi'
import { bbCard } from './betBuilderStyles'

type Props = {
  summary: BetBuilderOpportunitiesSummary
  fixturesWithOpportunity: number
}

export function BetBuilderSummary({ summary, fixturesWithOpportunity }: Props) {
  const eligible =
    typeof summary.fixtures_eligible_total === 'number'
      ? summary.fixtures_eligible_total
      : summary.fixtures_considered

  const items: Array<{ key: string; label: string; value: number }> = [
    { key: 'fixtures_eligible_total', label: 'Fixture', value: eligible ?? 0 },
    {
      key: 'fixtures_with_opportunity',
      label: 'Con opportunity',
      value: fixturesWithOpportunity,
    },
    {
      key: 'opportunities_total',
      label: 'Opportunity',
      value: summary.opportunities_total ?? 0,
    },
    { key: 'price_only', label: 'Solo quota', value: summary.price_only ?? 0 },
    { key: 'signals_only', label: 'Solo segnali', value: summary.signals_only ?? 0 },
    {
      key: 'price_and_signals',
      label: 'Quota + segnali',
      value: summary.price_and_signals ?? 0,
    },
  ]

  return (
    <section aria-label="Summary giornata" data-testid="bet-builder-summary">
      <div
        className={`${bbCard} -mx-1 grid grid-cols-3 gap-0 overflow-hidden sm:mx-0 sm:flex sm:overflow-x-auto lg:grid lg:grid-cols-6 lg:overflow-visible`}
      >
        {items.map((item, i) => (
          <div
            key={item.key}
            className={`min-w-0 px-2.5 py-2 sm:min-w-[6.5rem] sm:shrink-0 sm:px-3 sm:py-2.5 ${
              i > 0 ? 'border-l border-slate-100' : ''
            }`}
            data-testid={`summary-${item.key}`}
          >
            <p className="text-base font-semibold tabular-nums text-slate-900 sm:text-lg">
              {item.value}
            </p>
            <p className="mt-0.5 text-[10px] font-medium leading-tight text-slate-500 sm:text-[11px]">
              {item.label}
            </p>
          </div>
        ))}
      </div>
    </section>
  )
}
