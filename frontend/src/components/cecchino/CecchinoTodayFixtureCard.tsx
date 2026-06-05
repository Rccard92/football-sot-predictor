import { useState } from 'react'
import type { CecchinoTodayListFixture } from '../../lib/cecchinoTodayApi'
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

function resultBlock(fixture: CecchinoTodayListFixture): { label: string; value: string } {
  const score = fixture.score
  const showScore = score?.available && score.home != null && score.away != null

  if (fixture.status === 'finished') {
    return {
      label: 'Risultato finale',
      value: showScore ? `${score.home} – ${score.away}` : '—',
    }
  }
  if (fixture.status === 'live') {
    return {
      label: 'Live',
      value: showScore ? `${score.home} – ${score.away}` : '—',
    }
  }
  return { label: 'Risultato', value: '—' }
}

export function CecchinoTodayFixtureCard({ fixture, selected, onSelect }: Props) {
  const isFinished = fixture.status === 'finished'
  const result = resultBlock(fixture)

  const cardVariant = selected
    ? todayFixtureCardSelected
    : isFinished
      ? todayFixtureCardFinished
      : todayFixtureCardDefault

  return (
    <article className={`${todayFixtureCardBase} ${cardVariant}`}>
      <div className="flex items-start gap-3">
        <div className="flex w-20 shrink-0 flex-col items-start gap-1">
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
          <div className="flex items-start gap-2">
            <SafeImg src={fixture.home_team_logo_url} alt="" className="mt-0.5 h-6 w-6 shrink-0 object-contain" />
            <span className="line-clamp-2 break-words font-semibold leading-snug text-slate-900">
              {fixture.home_team_name}
            </span>
          </div>
          <div className="flex items-start gap-2">
            <SafeImg src={fixture.away_team_logo_url} alt="" className="mt-0.5 h-6 w-6 shrink-0 object-contain" />
            <span className="line-clamp-2 break-words font-semibold leading-snug text-slate-900">
              {fixture.away_team_name}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center">
          <button
            type="button"
            onClick={onSelect}
            className="whitespace-nowrap rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-700"
          >
            {isFinished ? 'Rivedi analisi' : 'Apri analisi'}
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 border-t border-slate-100 pt-3">
        <div className="rounded-lg bg-slate-50 px-3 py-2">
          <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
            Predizione consigliata
          </p>
          <p className="mt-0.5 text-sm font-medium text-slate-800">
            {fixture.cecchino_recommended_prediction?.label ?? 'In arrivo'}
          </p>
        </div>
        <div className="rounded-lg bg-slate-50 px-3 py-2">
          <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{result.label}</p>
          <p className="mt-0.5 font-mono text-sm font-semibold tabular-nums text-slate-800">{result.value}</p>
        </div>
      </div>
    </article>
  )
}
