import type {
  DrawCredibilityCohortTargetSummary,
  DrawCredibilityStatisticsResponse,
} from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  maturity: DrawCredibilityStatisticsResponse['research_maturity']
  performance: DrawCredibilityStatisticsResponse['performance']
  primarySummary?: DrawCredibilityCohortTargetSummary | null
}

export function DrawCredibilityResearchMaturityPanel({
  maturity,
  performance,
  primarySummary,
}: Props) {
  const leagueNames =
    primarySummary?.distinct_league_names_count ?? primarySummary?.league_count
  const countryLeaguePairs = primarySummary?.distinct_country_league_pairs_count
  const countries =
    primarySummary?.distinct_countries_count ?? primarySummary?.country_count

  return (
    <section className="rounded-2xl border border-amber-200/80 bg-amber-50/50 p-4 shadow-sm">
      <h3 className="mb-2 text-sm font-semibold text-amber-900">Maturità ricerca</h3>
      <div className="grid gap-2 text-sm text-amber-950 sm:grid-cols-2 lg:grid-cols-4">
        <p>
          <span className="font-medium">Status:</span> {maturity.status}
        </p>
        <p>
          <span className="font-medium">Campione:</span> {maturity.sample_size} righe /{' '}
          {maturity.positive_events} pareggi
        </p>
        <p>
          <span className="font-medium">Periodo:</span> {maturity.time_span_days} giorni
          {maturity.short_time_span ? ' (breve)' : ''}
        </p>
        <p>
          <span className="font-medium">Tempo calcolo:</span> {performance.total_ms.toFixed(0)} ms
        </p>
      </div>
      {primarySummary ? (
        <div className="mt-3 grid gap-2 text-sm text-amber-950 sm:grid-cols-3">
          <p>
            <span className="font-medium">Nomi campionato distinti:</span>{' '}
            {typeof leagueNames === 'number' ? leagueNames : '—'}
          </p>
          <p>
            <span className="font-medium">Competizioni paese/campionato:</span>{' '}
            {typeof countryLeaguePairs === 'number' ? countryLeaguePairs : '—'}
          </p>
          <p>
            <span className="font-medium">Paesi:</span>{' '}
            {typeof countries === 'number' ? countries : '—'}
          </p>
        </div>
      ) : null}
      {maturity.warnings.length > 0 ? (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-800">
          {maturity.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
