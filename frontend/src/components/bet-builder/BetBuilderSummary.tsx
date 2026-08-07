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
    { key: 'fixtures_eligible_total', label: 'Fixture eleggibili', value: eligible ?? 0 },
    {
      key: 'fixtures_with_opportunity',
      label: 'Partite con opportunity',
      value: fixturesWithOpportunity,
    },
    {
      key: 'opportunities_total',
      label: 'Opportunity',
      value: summary.opportunities_total ?? 0,
    },
    { key: 'price_only', label: 'Solo quota', value: summary.price_only ?? 0 },
    { key: 'signals_only', label: 'Solo Segnali', value: summary.signals_only ?? 0 },
    {
      key: 'price_and_signals',
      label: 'Quota + Segnali',
      value: summary.price_and_signals ?? 0,
    },
  ]

  return (
    <section aria-label="Summary giornata" className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-800">Summary</h2>
      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 sm:grid sm:grid-cols-2 sm:overflow-visible md:grid-cols-3 lg:grid-cols-6">
        {items.map((item) => (
          <div
            key={item.key}
            className={`${bbCard} min-w-[140px] shrink-0 px-3 py-3 sm:min-w-0`}
            data-testid={`summary-${item.key}`}
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              {item.label}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{item.value}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
