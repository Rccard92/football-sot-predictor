import { useState } from 'react'
import type { CecchinoTodayListFixture, CecchinoTodayScoreSide } from '../../lib/cecchinoTodayApi'
import { formatKickoffTime, statusBadgeClass } from '../../lib/cecchinoTodayApi'
import {
  todayFixtureCardBase,
  todayFixtureCardDefault,
  todayFixtureCardFinished,
  todayFixtureCardSelected,
} from './cecchinoTodayStyles'

function SafeImg({ src, alt, className }: { src: string | null | undefined; alt: string; className: string }) {
  const [hidden, setHidden] = useState(false)
  if (!src || hidden) return null
  return (
    <img
      src={src}
      alt={alt}
      className={className}
      loading="lazy"
      onError={() => setHidden(true)}
    />
  )
}

type Props = {
  fixture: CecchinoTodayListFixture
  selected: boolean
  onSelect: () => void
}

function formatScore(side: CecchinoTodayScoreSide | undefined): string {
  if (!side?.available || side.home == null || side.away == null) return '—'
  return `${side.home} – ${side.away}`
}

export function CecchinoTodayFixtureCard({ fixture, selected, onSelect }: Props) {
  const isFinished = fixture.status === 'finished'
  const cardVariant = selected
    ? todayFixtureCardSelected
    : isFinished
      ? todayFixtureCardFinished
      : todayFixtureCardDefault

  const home = fixture.home_team_name ?? '—'
  const away = fixture.away_team_name ?? '—'

  return (
    <article className={`${todayFixtureCardBase} ${cardVariant}`}>
      <div className="flex items-start gap-3">
        <div className="flex w-[4.5rem] shrink-0 flex-col items-start gap-1.5">
          <span className="font-mono text-base font-bold tabular-nums text-blue-700 sm:text-lg">
            {formatKickoffTime(fixture.kickoff)}
          </span>
          <span
            className={`inline-flex max-w-full rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase leading-tight ring-1 sm:text-[10px] ${statusBadgeClass(fixture.status)}`}
          >
            {fixture.status_label}
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <SafeImg
              src={fixture.home_team_logo_url}
              alt=""
              className="h-5 w-5 shrink-0 object-contain sm:h-6 sm:w-6"
            />
            <span className="break-words text-sm font-semibold leading-snug text-slate-900 sm:text-base">
              {home}
            </span>
            <span className="shrink-0 text-xs font-medium text-slate-400 sm:text-sm">vs</span>
            <SafeImg
              src={fixture.away_team_logo_url}
              alt=""
              className="h-5 w-5 shrink-0 object-contain sm:h-6 sm:w-6"
            />
            <span className="break-words text-sm font-semibold leading-snug text-slate-900 sm:text-base">
              {away}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-start">
          <button
            type="button"
            onClick={onSelect}
            className="whitespace-nowrap rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-700"
          >
            {isFinished ? 'Rivedi analisi' : 'Apri analisi'}
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 sm:gap-3">
        <div className="min-w-0 rounded-lg bg-slate-50 px-2 py-2 sm:px-3">
          <p className="text-[9px] font-medium uppercase tracking-wide text-slate-500 sm:text-[10px]">
            Predizione
          </p>
          <p className="mt-0.5 truncate text-xs font-medium text-slate-800 sm:text-sm">
            {fixture.cecchino_recommended_prediction?.label ?? 'In arrivo'}
          </p>
        </div>
        <div className="min-w-0 rounded-lg bg-slate-50 px-2 py-2 sm:px-3">
          <p className="text-[9px] font-medium uppercase tracking-wide text-slate-500 sm:text-[10px]">
            PT
          </p>
          <p className="mt-0.5 font-mono text-xs font-semibold tabular-nums text-slate-800 sm:text-sm">
            {formatScore(fixture.score?.halftime)}
          </p>
        </div>
        <div className="min-w-0 rounded-lg bg-slate-50 px-2 py-2 sm:px-3">
          <p className="text-[9px] font-medium uppercase tracking-wide text-slate-500 sm:text-[10px]">
            FT
          </p>
          <p className="mt-0.5 font-mono text-xs font-semibold tabular-nums text-slate-800 sm:text-sm">
            {formatScore(fixture.score?.fulltime)}
          </p>
        </div>
      </div>
    </article>
  )
}
