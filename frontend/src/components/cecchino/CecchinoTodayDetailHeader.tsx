import type { CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { todayBadgeActive, todayCard, todayCardPadding } from './cecchinoTodayStyles'

type Props = {
  detail: CecchinoTodayDetailResponse
}

export function CecchinoTodayDetailHeader({ detail }: Props) {
  return (
    <header className={`${todayCard} ${todayCardPadding}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            {detail.country_name} — {detail.league_name}
          </p>
          <h2 className="mt-1 text-xl font-bold text-slate-900 sm:text-2xl">
            {detail.home_team_name}{' '}
            <span className="font-normal text-slate-400">vs</span>{' '}
            {detail.away_team_name}
          </h2>
          {detail.kickoff && (
            <p className="mt-2 text-sm text-slate-600">
              Kickoff{' '}
              <span className="font-medium tabular-nums text-slate-800">
                {new Date(detail.kickoff).toLocaleString('it-IT', { timeZone: 'Europe/Rome' })}
              </span>
            </p>
          )}
        </div>
        <span className={todayBadgeActive}>Analizzabile</span>
      </div>
    </header>
  )
}
