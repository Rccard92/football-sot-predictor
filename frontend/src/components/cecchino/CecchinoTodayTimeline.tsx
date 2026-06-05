import type { CecchinoTodayDay } from '../../lib/cecchinoTodayApi'
import { formatDayShort } from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding } from './cecchinoTodayStyles'

type Props = {
  days: CecchinoTodayDay[]
  selectedDay: string
  onSelectDay: (date: string) => void
}

export function CecchinoTodayTimeline({ days, selectedDay, onSelectDay }: Props) {
  if (!days.length) return null

  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <p className="mb-3 text-sm font-medium text-slate-800">Timeline giornaliera</p>
      <div className="-mx-1 flex gap-2 overflow-x-auto pb-1 snap-x snap-mandatory">
        {days.map((day) => {
          const active = day.date === selectedDay
          const countLabel = day.is_scanned ? String(day.eligible_count) : '—'
          return (
            <button
              key={day.date}
              type="button"
              onClick={() => onSelectDay(day.date)}
              className={`min-w-[88px] shrink-0 snap-start rounded-xl border px-3 py-2.5 text-center transition ${
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
              <div className={`mt-1 text-lg font-bold tabular-nums ${day.is_today && !active ? 'text-blue-700' : ''}`}>
                {countLabel}
              </div>
              <div className={`mt-0.5 text-[10px] ${active ? 'text-blue-100' : 'text-slate-400'}`}>
                {day.is_scanned ? 'Scansionata' : 'Non scansionata'}
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}
