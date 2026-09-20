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
import { fmtDateShort, fmtDayLabel } from './format'

type Props = {
  days: V4Day[]
  selectedDay: string
  today: string
  onSelectDay: (date: string) => void
}

function weekday(dateIso: string): string {
  return fmtDayLabel(dateIso).split(' ')[0] ?? dateIso
}

/** Selettore a 7 giorni con le pillole compatte di CecchinoDayTimeline: giorno, data, partite, giocate. */
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
      <p className="mb-3 text-sm font-medium text-slate-800">Giorni</p>
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
            const playsBadge = active
              ? 'bg-white/20 text-white'
              : day.plays > 0
                ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/80'
                : 'bg-slate-100 text-slate-500 ring-1 ring-slate-200'
            return (
              <button
                key={day.date}
                type="button"
                onClick={() => onSelectDay(day.date)}
                aria-pressed={active}
                aria-label={`${fmtDayLabel(day.date)}, ${day.fixtures} partite, ${day.plays} giocate`}
                className={`rounded-xl border px-2 py-2.5 text-center transition sm:px-3 ${
                  active
                    ? 'border-blue-500 bg-blue-600 text-white shadow-md ring-2 ring-blue-300'
                    : day.fixtures > 0
                      ? 'border-slate-300 bg-white text-slate-900 hover:border-blue-300'
                      : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300'
                }`}
              >
                <div className={`text-xs ${isToday && !active ? 'font-bold' : 'font-medium'}`}>
                  {weekday(day.date)}
                  {isToday ? (
                    <span className={`ml-1 rounded px-1 text-xs ${active ? 'bg-white/20' : 'bg-blue-100 text-blue-700'}`}>
                      Oggi
                    </span>
                  ) : null}
                </div>
                <div className={`mt-0.5 text-xs ${active ? 'text-blue-100' : 'text-slate-500'}`}>
                  {fmtDateShort(day.date)}
                </div>
                <div className={`mt-1 text-lg font-bold tabular-nums ${isToday && !active ? 'text-blue-700' : ''}`}>
                  {day.fixtures}
                </div>
                <div className={`text-xs ${active ? 'text-blue-100' : 'text-slate-400'}`}>
                  {day.fixtures === 1 ? 'partita' : 'partite'}
                </div>
                <div className="mt-1.5">
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${playsBadge}`}>
                    {day.plays} {day.plays === 1 ? 'giocata' : 'giocate'}
                  </span>
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
