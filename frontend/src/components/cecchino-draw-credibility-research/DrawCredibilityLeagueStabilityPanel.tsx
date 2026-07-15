type Props = {
  league: Record<string, unknown>
  marketSummary: { league_count: number; country_count: number }
}

export function DrawCredibilityLeagueStabilityPanel({ league, marketSummary }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Stabilità per lega</h3>
      <div className="grid gap-2 text-sm text-slate-700 sm:grid-cols-3">
        <p>
          <span className="font-medium">Leghe distinte:</span> {marketSummary.league_count}
        </p>
        <p>
          <span className="font-medium">Paesi:</span> {marketSummary.country_count}
        </p>
        <p>
          <span className="font-medium">Fragmented:</span>{' '}
          {league.fragmented_leagues ? 'Sì' : 'No'}
        </p>
      </div>
    </section>
  )
}
