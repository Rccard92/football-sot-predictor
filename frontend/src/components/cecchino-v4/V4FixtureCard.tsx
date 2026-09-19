import type { V4FixtureCard as V4FixtureCardData } from '../../lib/cecchinoV4Api'
import {
  todayFixtureCardBase,
  todayFixtureCardDefault,
  todayFixtureCardFinished,
  todayFixtureCardSelected,
} from '../cecchino/cecchinoTodayStyles'
import { noPlayReasonLabel, V4_UNCERTAINTY_BAR, V4_UNCERTAINTY_LABELS, v4Label } from './constants'
import { fmtGoalsRange, fmtPct, fmtProfit, fmtQuota, fmtScore, fmtTimeRome } from './format'
import { V4LineupsDot } from './V4Chips'

type Props = {
  fixture: V4FixtureCardData
  selected: boolean
  onSelect: (id: number) => void
}

const LIVE = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT'])
const FINISHED = new Set(['FT', 'AET', 'PEN'])

function statusWord(status: string): string | null {
  if (LIVE.has(status)) return 'In corso'
  if (FINISHED.has(status)) return 'Finita'
  if (status === 'PST') return 'Rinviata'
  if (status === 'CANC') return 'Annullata'
  if (status === 'ABD') return 'Sospesa'
  return null
}

export function V4UncertaintyBar({ score, level }: { score: number; level: keyof typeof V4_UNCERTAINTY_BAR }) {
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100)
  return (
    <div className="flex items-center gap-3" aria-label={`${V4_UNCERTAINTY_LABELS[level]}, ${pct} su 100`}>
      <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-200" aria-hidden>
        <div className={`h-full rounded-full ${V4_UNCERTAINTY_BAR[level]}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="shrink-0 text-base text-slate-600">{V4_UNCERTAINTY_LABELS[level]}</span>
    </div>
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
      className={`${todayFixtureCardBase} ${cls} space-y-2`}
      data-testid="v4-fixture-card"
      data-fixture-id={fixture.id}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={v4Label}>
            {fixture.competition} · {fmtTimeRome(fixture.kickoff_at)}
            {status ? ` · ${status}` : ''}
          </p>
          <h3 className="truncate text-xl font-semibold text-slate-900">
            {fixture.home_team} - {fixture.away_team}
          </h3>
        </div>
        <V4LineupsDot status={fixture.lineups_status} withText={false} />
      </div>

      {fixture.result ? (
        <p className="text-base text-slate-800">
          Finita <span className="font-semibold tabular-nums">{fmtScore(fixture.result.ft_home, fixture.result.ft_away)}</span>
          {fixture.result.ht_home != null && fixture.result.ht_away != null
            ? ` (primo tempo ${fmtScore(fixture.result.ht_home, fixture.result.ht_away)})`
            : ''}
        </p>
      ) : null}

      {fixture.most_likely || fixture.expected_goals ? (
        <p className="text-base text-slate-700">
          {fixture.most_likely ? (
            <>
              Segno più probabile <span className="font-semibold">{fixture.most_likely.label}</span> al{' '}
              <span className="tabular-nums">{fmtPct(fixture.most_likely.p)}</span>
            </>
          ) : null}
          {fixture.most_likely && fixture.expected_goals ? ' · ' : ''}
          {fixture.expected_goals ? (
            <>
              gol attesi{' '}
              <span className="tabular-nums">
                {fmtGoalsRange(fixture.expected_goals.home, fixture.expected_goals.away)}
              </span>
            </>
          ) : null}
        </p>
      ) : (
        <p className="text-base text-slate-500">Previsione non ancora calcolata</p>
      )}

      {play ? (
        <p className="text-base font-semibold text-emerald-700" data-testid="v4-best-play">
          {play.label} · {fmtPct(play.p)} · {fmtQuota(play.quota_used)} · {fmtProfit(play.expected_profit)}
        </p>
      ) : (
        <p className="text-base text-slate-500" data-testid="v4-no-play">
          Nessuna giocata: {noPlayReasonLabel(fixture.no_play_reason)}
        </p>
      )}

      {fixture.uncertainty ? (
        <V4UncertaintyBar score={fixture.uncertainty.score} level={fixture.uncertainty.level} />
      ) : null}
    </button>
  )
}
