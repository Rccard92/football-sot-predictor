import type { CecchinoTodayDetailResponse, CecchinoTodayScoreSide } from '../../lib/cecchinoTodayApi'
import { todayBadgeActive, todayCard, todayCardPadding } from './cecchinoTodayStyles'

type Props = {
  detail: CecchinoTodayDetailResponse
}

function scoreText(side: CecchinoTodayScoreSide | undefined): string | null {
  if (!side?.available || side.home == null || side.away == null) return null
  return `${side.home} – ${side.away}`
}

/** Risultato primo tempo e finale nell'intestazione: visibile appena la partita ha un punteggio. */
function DetailScore({ detail }: Props) {
  const ft = scoreText(detail.score?.fulltime)
  const ht = scoreText(detail.score?.halftime)
  if (!ft && !ht) return null
  const live = detail.match_display_status === 'live'
  return (
    <div className="flex items-stretch gap-2" data-testid="today-detail-score">
      <div className="min-w-[4.5rem] rounded-lg bg-slate-50 px-3 py-2 text-center">
        <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">PT</p>
        <p className="mt-0.5 font-mono text-base font-semibold tabular-nums text-slate-800">{ht ?? '—'}</p>
      </div>
      <div className="min-w-[4.5rem] rounded-lg bg-slate-50 px-3 py-2 text-center">
        <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{live ? 'Live' : 'Finale'}</p>
        <p className="mt-0.5 font-mono text-base font-semibold tabular-nums text-slate-900">{ft ?? '—'}</p>
      </div>
    </div>
  )
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
        <div className="flex flex-wrap items-start gap-3">
          <DetailScore detail={detail} />
          <span className={todayBadgeActive}>Analizzabile</span>
        </div>
      </div>
    </header>
  )
}
