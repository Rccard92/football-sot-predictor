import { useMemo, useState } from 'react'
import type { V4Day } from '../../lib/cecchinoV4Api'
import {
  todayCard,
  todayCardPadding,
  todayTimelineArrow,
  todayTimelineGrid,
} from '../cecchino/cecchinoTodayStyles'
import {
  centerWindowOnDate,
  clampWindowStart,
  useTimelineVisibleCount,
} from '../cecchino/useTimelineVisibleCount'
import { fmtDayLabel } from './format'
import { v4Label } from './constants'

type Props = {
  days: V4Day[]
  selectedDay: string
  today: string
  onSelectDay: (date: string) => void
}

/** Selettore a 7 giorni con la grafica di Cecchino Today, tutto a 16 px. */
export function V4DayTimeline({ days, selectedDay, today, onSelectDay }: Props) {
  const visibleCount = useTimelineVisibleCount()
  const daysKey = useMemo(() => days.map((d) => d.date).join('|'), [days])
  const defaultStart = useMemo(
    () => centerWindowOnDate(days, selectedDay, visibleCount),
    [days, selectedDay, visibleCount],
  )
  const [nav, setNav] = useState({ daysKey: '', anchor: '', pages: 0 })
  const pages = nav.daysKey === daysKey && nav.anchor === selectedDay ? nav.pages : 0

  if (!days.length) return null

  const maxStart = Math.max(0, days.length - visibleCount)
  const windowStart = clampWindowStart(defaultStart + pages * visibleCount, visibleCount, days.length)
  const visible = days.slice(windowStart, windowStart + visibleCount)
  const move = (delta: number) =>
    setNav((prev) => {
      const current = prev.daysKey === daysKey && prev.anchor === selectedDay ? prev.pages : 0
      return { daysKey, anchor: selectedDay, pages: current + delta }
    })

  return (
    <section className={`${todayCard} ${todayCardPadding}`} aria-label="Giorni">
      <p className={`${v4Label} mb-3`}>Giorni</p>
      <div className="flex items-stretch gap-2">
        <button
          type="button"
          onClick={() => move(-1)}
          disabled={windowStart <= 0}
          aria-label="Giorni precedenti"
          className={todayTimelineArrow}
        >
          ‹
        </button>
        <div className={`${todayTimelineGrid} min-w-0 flex-1`}>
          {visible.map((day) => {
            const active = day.date === selectedDay
            const isToday = day.date === today
            return (
              <button
                key={day.date}
                type="button"
                onClick={() => onSelectDay(day.date)}
                aria-pressed={active}
                aria-label={`${fmtDayLabel(day.date)}, ${day.fixtures} partite, ${day.plays} giocate`}
                className={`rounded-xl border px-2 py-3 text-center transition ${
                  active
                    ? 'border-blue-500 bg-blue-600 text-white shadow-md ring-2 ring-blue-300'
                    : day.fixtures > 0
                      ? 'border-slate-300 bg-white text-slate-900 hover:border-blue-300'
                      : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300'
                }`}
              >
                <div className={`text-base ${isToday ? 'font-bold' : 'font-medium'}`}>
                  {isToday ? 'Oggi' : fmtDayLabel(day.date)}
                </div>
                {isToday ? (
                  <div className={`text-base ${active ? 'text-blue-100' : 'text-slate-500'}`}>
                    {fmtDayLabel(day.date)}
                  </div>
                ) : null}
                <div className="mt-1 text-2xl font-bold tabular-nums">{day.fixtures}</div>
                <div className={`text-base ${active ? 'text-blue-100' : 'text-slate-500'}`}>
                  {day.fixtures === 1 ? 'partita' : 'partite'}
                </div>
                <div
                  className={`text-base font-semibold ${
                    active ? 'text-emerald-100' : day.plays > 0 ? 'text-emerald-700' : 'text-slate-400'
                  }`}
                >
                  {day.plays} {day.plays === 1 ? 'giocata' : 'giocate'}
                </div>
              </button>
            )
          })}
        </div>
        <button
          type="button"
          onClick={() => move(1)}
          disabled={windowStart >= maxStart}
          aria-label="Giorni successivi"
          className={todayTimelineArrow}
        >
          ›
        </button>
      </div>
    </section>
  )
}
