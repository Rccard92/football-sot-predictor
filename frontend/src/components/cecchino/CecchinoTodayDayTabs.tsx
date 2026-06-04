import { todayBadgeMuted, todayCard, todayCardPadding } from './cecchinoTodayStyles'
import type { CecchinoTodayDay } from '../../lib/cecchinoTodayApi'

type Props = {
  days: CecchinoTodayDay[]
  selectedDay: string
  onSelectDay: (date: string) => void
}

export function CecchinoTodayDayTabs({ days, selectedDay, onSelectDay }: Props) {
  if (!days.length) return null

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-3`}>
      <p className="text-sm font-medium text-slate-800">Giornate disponibili</p>
      <div className="flex flex-wrap gap-2">
        {days.map((day) => {
          const active = day.date === selectedDay
          return (
            <button
              key={day.date}
              type="button"
              onClick={() => onSelectDay(day.date)}
              className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition ${
                active
                  ? 'bg-blue-600 text-white shadow-sm ring-2 ring-blue-300'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              <span>{day.label}</span>
              <span className="text-xs opacity-80">{day.date.slice(5).replace('-', '/')}</span>
              <span className={active ? 'rounded-full bg-white/20 px-1.5 text-xs' : todayBadgeMuted}>
                {day.eligible_count}
              </span>
              {day.status === 'pending' && !active && (
                <span className={todayBadgeMuted}>non scansionata</span>
              )}
            </button>
          )
        })}
      </div>
    </section>
  )
}
