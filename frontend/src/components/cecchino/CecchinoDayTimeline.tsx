import { useMemo, useState } from 'react'
import type { CecchinoTodayDay } from '../../lib/cecchinoTodayApi'
import { formatDayShort } from '../../lib/cecchinoTodayApi'
import {
  todayCard,
  todayCardPadding,
  todayTimelineArrow,
  todayTimelineGrid,
} from './cecchinoTodayStyles'
import {
  centerWindowOnToday,
  clampWindowStart,
  useTimelineVisibleCount,
} from './useTimelineVisibleCount'

type Props = {
  days: CecchinoTodayDay[]
  selectedDay: string
  onSelectDay: (date: string) => void
}

export function CecchinoDayTimeline({ days, selectedDay, onSelectDay }: Props) {
  const visibleCount = useTimelineVisibleCount()
  const daysKey = useMemo(() => days.map((d) => d.date).join('|'), [days])
  const centerStart = useMemo(
    () => centerWindowOnToday(days, visibleCount),
    [days, visibleCount],
  )

  const [navState, setNavState] = useState({ daysKey: '', navPages: 0 })
  const navPages = navState.daysKey === daysKey ? navState.navPages : 0

  const setNavPages = (updater: (prev: number) => number) => {
    setNavState((prev) => {
      const currentPages = prev.daysKey === daysKey ? prev.navPages : 0
      return { daysKey, navPages: updater(currentPages) }
    })
  }

  if (!days.length) return null

  const maxStart = Math.max(0, days.length - visibleCount)
  const windowStart = clampWindowStart(centerStart + navPages * visibleCount, visibleCount, days.length)
  const canPrev = windowStart > 0
  const canNext = windowStart < maxStart
  const visibleDays = days.slice(windowStart, windowStart + visibleCount)

  const handlePrev = () => {
    setNavPages((prev) => prev - 1)
  }

  const handleNext = () => {
    setNavPages((prev) => prev + 1)
  }

  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <p className="mb-3 text-sm font-medium text-slate-800">Timeline giornaliera</p>
      <div className="flex items-stretch gap-2">
        <button
          type="button"
          onClick={handlePrev}
          disabled={!canPrev}
          aria-label="Giorni precedenti"
          className={todayTimelineArrow}
        >
          ‹
        </button>

        <div className={`${todayTimelineGrid} min-w-0 flex-1`}>
          {visibleDays.map((day) => {
            const active = day.date === selectedDay
            const countLabel = day.is_scanned ? String(day.eligible_count) : '—'
            return (
              <button
                key={day.date}
                type="button"
                onClick={() => onSelectDay(day.date)}
                className={`rounded-xl border px-2 py-2.5 text-center transition sm:px-3 ${
                  active
                    ? 'border-blue-500 bg-blue-600 text-white shadow-md ring-2 ring-blue-300'
                    : day.is_scanned && day.eligible_count > 0
                      ? 'border-slate-300 bg-white text-slate-900 hover:border-blue-300'
                      : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300'
                }`}
              >
                <div className={`text-xs ${day.is_today && !active ? 'font-bold' : 'font-medium'}`}>
                  {day.label}
                  {day.is_today && (
                    <span
                      className={`ml-1 rounded px-1 text-[10px] ${
                        active ? 'bg-white/20' : 'bg-blue-100 text-blue-700'
                      }`}
                    >
                      Oggi
                    </span>
                  )}
                </div>
                <div className={`mt-0.5 text-[11px] ${active ? 'text-blue-100' : 'text-slate-500'}`}>
                  {formatDayShort(day.date)}
                </div>
                <div
                  className={`mt-1 text-lg font-bold tabular-nums ${day.is_today && !active ? 'text-blue-700' : ''}`}
                >
                  {countLabel}
                </div>
                <div className={`mt-0.5 text-[10px] ${active ? 'text-blue-100' : 'text-slate-400'}`}>
                  {day.is_scanned ? 'Scansionata' : 'Non scansionata'}
                </div>
              </button>
            )
          })}
        </div>

        <button
          type="button"
          onClick={handleNext}
          disabled={!canNext}
          aria-label="Giorni successivi"
          className={todayTimelineArrow}
        >
          ›
        </button>
      </div>
    </section>
  )
}
