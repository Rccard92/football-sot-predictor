import { useMemo, useState } from 'react'
import { OverviewFilters } from './overview/OverviewFilters'
import { MarketPulse } from './overview/MarketPulse'
import { Outcomes1x2 } from './overview/Outcomes1x2'
import { GoalLandscape } from './overview/GoalLandscape'
import { MarketCalibration } from './overview/MarketCalibration'
import { FlatRoiExplorer } from './overview/FlatRoiExplorer'
import { OddsMovementPanel } from './overview/OddsMovementPanel'
import { LeagueDnaTable } from './overview/LeagueDnaTable'
import { BettingInsights } from './overview/BettingInsights'
import { useAnalyticsOverview } from './overview/useAnalyticsOverview'
import type { CecchinoLabAnalyticsFilters } from '../../lib/cecchinoLabApi'

type Props = {
  refreshKey: number
  onGoImport: () => void
}

const EMPTY_FILTERS = { season_label: '', country: '', competition: '' }

function Skeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-24 rounded-2xl" style={{ background: 'var(--lab-surface)' }} />
        ))}
      </div>
      <div className="h-48 rounded-2xl" style={{ background: 'var(--lab-surface)' }} />
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="h-64 rounded-2xl" style={{ background: 'var(--lab-surface)' }} />
        <div className="h-64 rounded-2xl" style={{ background: 'var(--lab-surface)' }} />
      </div>
    </div>
  )
}

export function OverviewTab({ refreshKey, onGoImport }: Props) {
  const [filters, setFilters] = useState(EMPTY_FILTERS)

  const apiFilters: CecchinoLabAnalyticsFilters = useMemo(
    () => ({
      season_label: filters.season_label || undefined,
      country: filters.country || undefined,
      competition: filters.competition || undefined,
    }),
    [filters],
  )

  const { data, loading, error } = useAnalyticsOverview(apiFilters, refreshKey)

  if (error) {
    return (
      <div className="p-8 text-sm" style={{ color: 'var(--lab-err)' }}>
        {error}
      </div>
    )
  }

  if (!loading && data?.is_empty) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 px-6 py-20 text-center">
        <div
          className="flex h-16 w-16 items-center justify-center rounded-2xl text-2xl"
          style={{ background: 'var(--lab-cyan-dim)', color: 'var(--lab-cyan)' }}
        >
          ⧉
        </div>
        <h2 className="text-2xl font-semibold">Nessun dataset storico</h2>
        <p className="max-w-md text-sm" style={{ color: 'var(--lab-muted)' }}>
          Importa i CSV di football-data.co.uk per costruire l&apos;archivio isolato del Cecchino Lab.
          Nessuna formula e nessun impatto su Cecchino Today.
        </p>
        <button type="button" className="lab-btn" onClick={onGoImport}>
          Importa CSV
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <OverviewFilters
        available={data?.available_filters}
        filters={filters}
        sample={data?.sample}
        onChange={setFilters}
        onReset={() => setFilters(EMPTY_FILTERS)}
      />

      {loading || !data ? (
        <Skeleton />
      ) : (
        <>
          <MarketPulse summary={data.summary} />

          <div className="grid gap-4 lg:grid-cols-2">
            <Outcomes1x2 outcomes={data.outcomes_1x2} />
            <GoalLandscape goals={data.goals} firstHalf={data.first_half} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <MarketCalibration favorite={data.favorite} />
            <FlatRoiExplorer outcomes={data.outcomes_1x2} goals={data.goals} />
          </div>

          <OddsMovementPanel movement={data.odds_movement} margins={data.margins} />

          <LeagueDnaTable
            leagues={data.leagues}
            onSelectCompetition={(name) => {
              const comp = data.available_filters.competitions.find((c) => c.name === name)
              setFilters((f) => ({
                ...f,
                competition: name,
                country: comp?.country || f.country,
              }))
            }}
          />

          <BettingInsights insights={data.insights} />

          {data.longest_odds_hit.record_match ? (
            <div
              className="rounded-2xl p-4 text-sm"
              style={{ border: '1px solid var(--lab-border)', background: 'rgba(192,132,252,0.06)' }}
            >
              <div className="text-xs uppercase tracking-wider" style={{ color: '#c084fc' }}>
                Record esito più quotato centrato
              </div>
              <div className="mt-1">
                {data.longest_odds_hit.record_match.home_team} – {data.longest_odds_hit.record_match.away_team}
                {' · '}
                {data.longest_odds_hit.record_match.result}
                {' · '}
                sel. {data.longest_odds_hit.record_match.selection} @ {data.longest_odds_hit.record_match.odds}
                {' · '}
                {data.longest_odds_hit.record_match.competition_name} {data.longest_odds_hit.record_match.season_label}
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
