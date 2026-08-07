import type { BetBuilderOpportunitiesSummary } from '../../lib/cecchinoBetBuilderApi'
import { bbCard } from './betBuilderStyles'

type Props = {
  summary: BetBuilderOpportunitiesSummary
}

const ITEMS: Array<{
  key: keyof Pick<
    BetBuilderOpportunitiesSummary,
    | 'fixtures_eligible_total'
    | 'fixtures_considered'
    | 'opportunities_total'
    | 'price_only'
    | 'signals_only'
    | 'price_and_signals'
  >
  label: string
  fallbackKey?: 'fixtures_considered'
}> = [
  { key: 'fixtures_eligible_total', label: 'Fixture eleggibili', fallbackKey: 'fixtures_considered' },
  { key: 'opportunities_total', label: 'Opportunity' },
  { key: 'price_only', label: 'Solo quota' },
  { key: 'signals_only', label: 'Solo Segnali' },
  { key: 'price_and_signals', label: 'Quota + Segnali' },
]

export function BetBuilderSummary({ summary }: Props) {
  return (
    <section aria-label="Summary giornata" className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-800">Summary</h2>
      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 sm:grid sm:grid-cols-2 sm:overflow-visible md:grid-cols-5">
        {ITEMS.map((item) => {
          const raw =
            item.key === 'fixtures_eligible_total'
              ? (summary.fixtures_eligible_total ?? summary.fixtures_considered)
              : summary[item.key]
          const value = typeof raw === 'number' ? raw : 0
          return (
            <div
              key={item.key}
              className={`${bbCard} min-w-[140px] shrink-0 px-3 py-3 sm:min-w-0`}
              data-testid={`summary-${item.key}`}
            >
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                {item.label}
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
            </div>
          )
        })}
      </div>
    </section>
  )
}
