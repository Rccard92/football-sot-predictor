import type { CecchinoTodayListFixture } from '../../lib/cecchinoTodayApi'
import { formatKickoffTime } from '../../lib/cecchinoTodayApi'
import {
  todayBadgeActive,
  todayBadgeOk,
  todayBadgeMuted,
  todayFixtureCardBase,
  todayFixtureCardDefault,
  todayFixtureCardSelected,
} from './cecchinoTodayStyles'

type Props = {
  fixture: CecchinoTodayListFixture
  country: string
  league: string
  selected: boolean
  onSelect: () => void
}

const BOOKMAKERS = ['Bet365', 'Betfair', 'Pinnacle'] as const

function BookmakerBadge({ name, ok }: { name: string; ok: boolean }) {
  return (
    <span className={ok ? todayBadgeOk : todayBadgeMuted}>
      {name} {ok ? 'OK' : '—'}
    </span>
  )
}

export function CecchinoTodayFixtureCard({
  fixture,
  country,
  league,
  selected,
  onSelect,
}: Props) {
  const bm = fixture.bookmakers || {}
  const statsOk = fixture.stats_status === 'ok'

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`${todayFixtureCardBase} ${
        selected ? todayFixtureCardSelected : todayFixtureCardDefault
      }`}
    >
      <div className="flex gap-3">
        <div className="flex shrink-0 flex-col items-center justify-center rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-slate-200">
          <span className="font-mono text-lg font-bold tabular-nums text-blue-700">
            {formatKickoffTime(fixture.kickoff)}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="font-semibold text-slate-900">
              {fixture.home_team_name}{' '}
              <span className="font-normal text-slate-500">vs</span>{' '}
              {fixture.away_team_name}
            </p>
            {selected && <span className={todayBadgeActive}>Analizzabile</span>}
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {country} · {league}
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {BOOKMAKERS.map((name) => (
              <BookmakerBadge key={name} name={name} ok={bm[name] === 'OK'} />
            ))}
            <span className={statsOk ? todayBadgeOk : todayBadgeMuted}>
              Stats {statsOk ? 'OK' : '—'}
            </span>
          </div>
        </div>
      </div>
    </button>
  )
}
