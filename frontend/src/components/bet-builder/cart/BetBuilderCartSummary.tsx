import { formatCombinedOddsDisplay } from './betBuilderCartUtils'

type Props = {
  selectionCount: number
  combinedOdds: number | null
}

export function BetBuilderCartSummary({ selectionCount, combinedOdds }: Props) {
  const display = formatCombinedOddsDisplay(combinedOdds)
  const incomplete = selectionCount > 0 && combinedOdds == null
  const multi = selectionCount >= 2

  return (
    <div
      className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3"
      data-testid="bet-builder-cart-summary"
    >
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {selectionCount === 1
              ? '1 selezione'
              : `${selectionCount} selezioni`}
          </p>
          {multi ? (
            <p className="mt-0.5 text-xs text-slate-500">Combinazione manuale</p>
          ) : null}
          <p className="mt-2 text-sm font-medium text-slate-700">Moltiplicatore quote</p>
        </div>
        <p
          className="text-2xl font-semibold tabular-nums tracking-tight text-slate-950"
          data-testid="bet-builder-cart-multiplier"
          aria-live="polite"
        >
          {selectionCount === 0 ? '—' : display === 'N/D' ? 'N/D' : `×${display}`}
        </p>
      </div>
      {incomplete ? (
        <p
          className="mt-2 text-xs text-amber-900"
          data-testid="bet-builder-cart-multiplier-incomplete"
        >
          Una o più quote non sono disponibili
        </p>
      ) : null}
    </div>
  )
}
