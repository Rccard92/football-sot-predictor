import type { CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import {
  todayBadgeActive,
  todayBadgeOk,
  todayBadgeMuted,
  todayCard,
  todayCardPadding,
} from './cecchinoTodayStyles'

type Props = {
  detail: CecchinoTodayDetailResponse
}

const BOOKMAKERS = ['Bet365', 'Betfair', 'Pinnacle'] as const

export function CecchinoTodayDetailHeader({ detail }: Props) {
  const odds = detail.odds_snapshot as { bookmakers?: Record<string, unknown> } | undefined
  const bmSnap = odds?.bookmakers || {}

  return (
    <header className={`${todayCard} ${todayCardPadding} space-y-4`}>
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

      <div className="flex flex-wrap gap-2">
        {BOOKMAKERS.map((name) => (
          <span
            key={name}
            className={name in bmSnap ? todayBadgeOk : todayBadgeMuted}
          >
            {name}
          </span>
        ))}
        <span className={todayBadgeOk}>Statistiche OK</span>
      </div>

      {detail.cecchino_link && (
        <a
          href={detail.cecchino_link}
          className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50"
        >
          Apri analisi Cecchino classica
        </a>
      )}
    </header>
  )
}
