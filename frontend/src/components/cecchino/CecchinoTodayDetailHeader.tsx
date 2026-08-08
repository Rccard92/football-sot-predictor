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

type OddsSnap = {
  bookmakers?: Record<string, unknown>
  selection_sources?: Record<string, string>
  raw_by_bookmaker_id?: Record<string, unknown>
  book_policy_version?: string
}

function _bookHasUsableOdds(entry: unknown): boolean {
  if (entry == null) return false
  if (Array.isArray(entry)) return entry.length > 0
  if (typeof entry !== 'object') return false
  const obj = entry as Record<string, unknown>
  // Snapshot 1X2: almeno una quota numerica utilizzabile
  for (const k of ['HOME', 'DRAW', 'AWAY']) {
    const v = obj[k]
    if (typeof v === 'number' && Number.isFinite(v) && v > 1) return true
    if (typeof v === 'string' && v.trim() !== '' && Number(v) > 1) return true
  }
  // Raw payload non vuoto
  return Object.keys(obj).length > 0
}

export function CecchinoTodayDetailHeader({ detail }: Props) {
  const odds = detail.odds_snapshot as OddsSnap | undefined
  const bmSnap = odds?.bookmakers || {}
  const rawMap = odds?.raw_by_bookmaker_id || {}
  // Availability reale del book: raw id oppure snapshot del book (mai Canonical)
  const betfairOk =
    _bookHasUsableOdds(rawMap['3']) || _bookHasUsableOdds(bmSnap.Betfair)
  const bet365Ok =
    _bookHasUsableOdds(rawMap['8']) || _bookHasUsableOdds(bmSnap.Bet365)
  const sources = odds?.selection_sources || {}
  const fallbackCount = Object.values(sources).filter((s) => s === 'Bet365').length

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

      <div className="space-y-2">
        <p className="text-xs text-slate-600">
          Book · <span className="font-medium text-slate-800">Betfair primario · Bet365 fallback</span>
        </p>
        <div className="flex flex-wrap gap-2">
          <span className={betfairOk ? todayBadgeOk : todayBadgeMuted}>
            Betfair {betfairOk ? 'OK' : 'N/D'}
          </span>
          <span className={bet365Ok ? todayBadgeOk : todayBadgeMuted}>
            Bet365 {bet365Ok ? 'OK' : 'N/D'}
          </span>
          {fallbackCount > 0 ? (
            <span className={todayBadgeMuted}>
              Fallback su {fallbackCount} selection 1X2
            </span>
          ) : null}
          <span className={todayBadgeOk}>Statistiche OK</span>
        </div>
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
            to={`/bookmakers?provider_fixture_id=${detail.provider_fixture_id}&bookmaker_ids=3,8`}
            className="inline-flex items-center rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-800 shadow-sm transition hover:bg-indigo-100"
          >
            Debug quote bookmaker
          </Link>
        ) : null}
      </div>
    </header>
  )
}
