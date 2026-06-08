import { Link } from 'react-router-dom'
import type { CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { CecchinoTodayTechnicalIds } from './CecchinoTodayTechnicalIds'
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

const BETFAIR_NAME = 'Betfair'

export function CecchinoTodayDetailHeader({ detail }: Props) {
  const odds = detail.odds_snapshot as { bookmakers?: Record<string, unknown> } | undefined
  const bmSnap = odds?.bookmakers || {}
  const betfairOk = BETFAIR_NAME in bmSnap

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

      <CecchinoTodayTechnicalIds detail={detail} />

      <div className="flex flex-wrap gap-2">
        <span className={betfairOk ? todayBadgeOk : todayBadgeMuted}>{BETFAIR_NAME}</span>
        <span className={todayBadgeOk}>Statistiche OK</span>
      </div>

      <div className="flex flex-wrap gap-2">
        {detail.cecchino_link && (
          <a
            href={detail.cecchino_link}
            className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50"
          >
            Apri analisi Cecchino classica
          </a>
        )}
        {detail.provider_fixture_id != null ? (
          <Link
            to={`/bookmakers?provider_fixture_id=${detail.provider_fixture_id}&bookmaker_ids=3`}
            className="inline-flex items-center rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-800 shadow-sm transition hover:bg-indigo-100"
          >
            Debug quote bookmaker
          </Link>
        ) : null}
      </div>
    </header>
  )
}
