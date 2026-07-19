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
  const ariaLabel = isFinished
    ? `Rivedi analisi ${home} contro ${away}`
    : `Apri analisi ${home} contro ${away}`

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-label={ariaLabel}
      aria-pressed={selected}
      className={`${todayFixtureCardBase} ${cardVariant} cursor-pointer`}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-base font-bold tabular-nums text-blue-700">
          {formatKickoffTime(fixture.kickoff)}
        </span>
        <span
          className={`inline-flex max-w-full rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase leading-tight ring-1 sm:text-[10px] ${statusBadgeClass(fixture.status)}`}
        >
          {fixture.status_label}
        </span>
        <span className="ml-auto shrink-0 text-lg leading-none text-slate-400" aria-hidden>
          ›
        </span>
      </div>

      <div className="mt-2.5 space-y-1.5">
        <div className="flex items-start gap-2">
          <SafeImg
            src={fixture.home_team_logo_url}
            alt=""
            className="mt-0.5 h-5 w-5 shrink-0 object-contain"
          />
          <span className="min-w-0 text-sm font-semibold leading-snug text-slate-900">{home}</span>
        </div>
        <p className="pl-7 text-[10px] font-medium uppercase tracking-wide text-slate-400">vs</p>
        <div className="flex items-start gap-2">
          <SafeImg
            src={fixture.away_team_logo_url}
            alt=""
            className="mt-0.5 h-5 w-5 shrink-0 object-contain"
          />
          <span className="min-w-0 text-sm font-semibold leading-snug text-slate-900">{away}</span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-[minmax(0,1.5fr)_minmax(55px,0.5fr)_minmax(55px,0.5fr)] gap-2 border-t border-slate-100 pt-3">
        <div className="min-w-0 rounded-lg bg-slate-50 px-2 py-2">
          <p className="text-[9px] font-medium uppercase tracking-wide text-slate-500">Predizione</p>
          <p className="mt-0.5 text-xs font-medium leading-snug text-slate-800">
            {fixture.cecchino_recommended_prediction?.label ?? 'In arrivo'}
          </p>
        </div>
        <div className="min-w-0 rounded-lg bg-slate-50 px-2 py-2">
          <p className="text-[9px] font-medium uppercase tracking-wide text-slate-500">PT</p>
          <p className="mt-0.5 font-mono text-xs font-semibold tabular-nums text-slate-800">
            {formatScore(fixture.score?.halftime)}
          </p>
        </div>
        <div className="min-w-0 rounded-lg bg-slate-50 px-2 py-2">
          <p className="text-[9px] font-medium uppercase tracking-wide text-slate-500">FT</p>
          <p className="mt-0.5 font-mono text-xs font-semibold tabular-nums text-slate-800">
            {formatScore(fixture.score?.fulltime)}
          </p>
        </div>
      </div>
    </button>
  )
}
