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
  /** Chiesto quando le frecce superano i giorni gia' caricati: sposta la finestra di `deltaDays` (anche nel passato). */
  onShiftWindow?: (deltaDays: number) => void
  /** Torna a oggi (data e finestra). */
  onToday?: () => void
}

function weekday(dateIso: string): string {
  return fmtDayLabel(dateIso).split(' ')[0] ?? dateIso
}

/** Selettore giorni con le pillole compatte di CecchinoDayTimeline: scorre avanti e indietro senza limiti (anche i giorni passati, con i risultati). */
export function V4DayTimeline({ days, selectedDay, today, onSelectDay, onShiftWindow, onToday }: Props) {
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
  const move = (delta: number) => {
    const atStart = delta < 0 && windowStart <= 0
    const atEnd = delta > 0 && windowStart >= maxStart
    if ((atStart || atEnd) && onShiftWindow) {
      onShiftWindow(delta * visibleCount)
      return
    }
    setNav((prev) => {
      const current = prev.daysKey === daysKey && prev.anchor === selectedDay ? prev.pages : 0
      return { daysKey, anchor: selectedDay, pages: current + delta }
    })
  }
  const todayVisible = visible.some((d) => d.date === today)

  return (
    <section className={`${todayCard} ${todayCardPadding}`} aria-label="Giorni">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-slate-800">Giorni</p>
        {onToday && (!todayVisible || selectedDay !== today) ? (
          <button
            type="button"
            onClick={onToday}
            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-blue-700 hover:border-blue-300"
          >
            Oggi
          </button>
        ) : null}
      </div>
      <div className="flex items-stretch gap-2">
        <button
          type="button"
          onClick={() => move(-1)}
          disabled={windowStart <= 0 && !onShiftWindow}
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
          disabled={windowStart >= maxStart && !onShiftWindow}
          aria-label="Giorni successivi"
          className={todayTimelineArrow}
        >
          ›
        </button>
      </div>
    </section>
  )
}
