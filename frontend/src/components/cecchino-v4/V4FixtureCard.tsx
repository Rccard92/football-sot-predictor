import type { V4FixtureCard as V4FixtureCardData, V4MarketRow } from '../../lib/cecchinoV4Api'
import {
  todayBadgeActive,
  todayBadgeMuted,
  todayFixtureCardBase,
  todayFixtureCardDefault,
  todayFixtureCardFinished,
  todayFixtureCardSelected,
} from '../cecchino/cecchinoTodayStyles'
import { noPlayReasonLabel, v4BadgeNoPlay, v4BadgeObserved, v4BadgePlay, v4Mono } from './constants'
import { fmtPct, fmtProfit, fmtQuota, fmtScore, fmtTimeRome } from './format'

type Props = {
  fixture: V4FixtureCardData
  selected: boolean
  onSelect: (id: number) => void
}

const LIVE = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT'])
const FINISHED = new Set(['FT', 'AET', 'PEN'])

function statusWord(status: string): string | null {
  if (LIVE.has(status)) return 'In corso'
  if (status === 'PST') return 'Rinviata'
  if (status === 'CANC') return 'Annullata'
  if (status === 'ABD') return 'Sospesa'
  return null
}

/**
 * Una riga sola per l'esito: etichetta della giocata, probabilita', quota e profitto.
 * Con `advised === false` la giocata e' in osservazione: grigia, non verde.
 */
export function V4PlayLine({ play, align = 'right' }: { play: V4MarketRow; align?: 'left' | 'right' }) {
  const observed = play.advised === false
  const profitOk = play.expected_profit != null && play.expected_profit >= 0.03
  return (
    <span
      className={`flex flex-wrap items-center gap-x-1.5 gap-y-1 ${align === 'right' ? 'justify-end' : ''}`}
      data-testid="v4-best-play"
    >
      <span className={observed ? v4BadgeObserved : v4BadgePlay}>{play.label}</span>{' '}
      {observed ? <span className="text-xs text-slate-500">· in osservazione </span> : null}
      <span className={`${v4Mono} text-xs text-slate-600`}>
        · {fmtPct(play.p)} · {fmtQuota(play.quota_used)} ·
      </span>{' '}
      <span
        className={`${v4Mono} text-xs font-semibold ${
          observed ? 'text-slate-600' : profitOk ? 'text-emerald-700' : 'text-slate-700'
        }`}
      >
        {fmtProfit(play.expected_profit)}
      </span>
    </span>
  )
}

export function V4FixtureCard({ fixture, selected, onSelect }: Props) {
  const finished = fixture.result != null || FINISHED.has(fixture.status)
  const status = statusWord(fixture.status)
  const play = fixture.best_play
  const cls = selected
    ? todayFixtureCardSelected
    : finished
      ? todayFixtureCardFinished
      : todayFixtureCardDefault

  return (
    <button
      type="button"
      onClick={() => onSelect(fixture.id)}
      aria-pressed={selected}
      aria-label={`${fixture.home_team} - ${fixture.away_team}, apri il ragionamento`}
      className={`${todayFixtureCardBase} ${cls} cursor-pointer`}
      data-testid="v4-fixture-card"
      data-fixture-id={fixture.id}
    >
      <div className="flex items-center gap-2">
        <span className={`${v4Mono} text-base font-bold text-blue-700`}>{fmtTimeRome(fixture.kickoff_at)}</span>
        <span className="min-w-0 truncate text-xs font-semibold uppercase tracking-wide text-slate-500">
          {fixture.competition}
        </span>
        {fixture.result ? (
          <span className={`${todayBadgeMuted} ${v4Mono}`}>
            Finita {fmtScore(fixture.result.ft_home, fixture.result.ft_away)}
          </span>
        ) : status ? (
          <span className={LIVE.has(fixture.status) ? todayBadgeActive : todayBadgeMuted}>{status}</span>
        ) : null}
        {fixture.lineups_status === 'ufficiali' ? (
          <span
            className="inline-block h-2 w-2 shrink-0 rounded-full bg-emerald-500"
            title="Formazioni ufficiali"
            aria-label="Formazioni ufficiali"
          />
        ) : null}
        <span className="ml-auto shrink-0 text-lg leading-none text-slate-400" aria-hidden>
          ›
        </span>
      </div>

      <div className="mt-2.5 flex items-center justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="truncate text-sm font-semibold leading-snug text-slate-900">{fixture.home_team}</p>
          <p className="truncate text-sm font-semibold leading-snug text-slate-900">{fixture.away_team}</p>
        </div>
        <div className="max-w-[62%] shrink-0 text-right">
          {play ? (
            <V4PlayLine play={play} />
          ) : (
            <span className={v4BadgeNoPlay} data-testid="v4-no-play">
              Nessuna giocata · {noPlayReasonLabel(fixture.no_play_reason)}
            </span>
          )}
        </div>
      </div>
    </button>
  )
}
