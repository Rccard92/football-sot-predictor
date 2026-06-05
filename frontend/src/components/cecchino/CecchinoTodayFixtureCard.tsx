import { useState } from 'react'
import type { CecchinoTodayListFixture } from '../../lib/cecchinoTodayApi'
import { formatKickoffTime, statusBadgeClass } from '../../lib/cecchinoTodayApi'
import {
  todayFixtureCardBase,
  todayFixtureCardDefault,
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

export function CecchinoTodayFixtureCard({ fixture, selected, onSelect }: Props) {
  const score = fixture.score
  const showScore = score?.available && score.home != null && score.away != null
  const isFinished = fixture.status === 'finished'

  return (
    <article
      className={`${todayFixtureCardBase} ${
        selected ? todayFixtureCardSelected : todayFixtureCardDefault
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex shrink-0 flex-col items-start gap-1 sm:w-24">
          <span className="font-mono text-lg font-bold tabular-nums text-blue-700">
            {formatKickoffTime(fixture.kickoff)}
          </span>
          <span
            className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ${statusBadgeClass(fixture.status)}`}
          >
            {fixture.status_label}
          </span>
        </div>

        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <SafeImg src={fixture.home_team_logo_url} alt="" className="h-6 w-6 object-contain" />
            <span className="truncate font-semibold text-slate-900">{fixture.home_team_name}</span>
          </div>
          <div className="flex items-center gap-2">
            <SafeImg src={fixture.away_team_logo_url} alt="" className="h-6 w-6 object-contain" />
            <span className="truncate font-semibold text-slate-900">{fixture.away_team_name}</span>
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2 sm:w-40">
          <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-2 py-1 text-center text-[10px] text-slate-600">
            <div className="font-medium">Predizione consigliata</div>
            <div>{fixture.cecchino_recommended_prediction?.label ?? 'In arrivo'}</div>
          </div>
          {showScore && (
            <div className="font-mono text-xl font-bold tabular-nums text-slate-900">
              {score.home} – {score.away}
            </div>
          )}
          <button
            type="button"
            onClick={onSelect}
            className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
          >
            {isFinished ? 'Rivedi analisi' : 'Apri analisi'}
          </button>
        </div>
      </div>
    </article>
  )
}
