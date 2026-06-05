import type { CecchinoTodayListSummary } from '../../lib/cecchinoTodayApi'
import { todayBadgeMuted, todayCard, todayCardPadding } from './cecchinoTodayStyles'

type Props = {
  selectedDay: string
  summary: CecchinoTodayListSummary | null
  isScanned: boolean
}

export function CecchinoTodayDaySummary({ selectedDay, summary, isScanned }: Props) {
  if (!isScanned || !summary) {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <p className="text-sm text-slate-600">
          Giornata <span className="font-medium text-slate-900">{selectedDay}</span> — non ancora
          scansionata.
        </p>
      </section>
    )
  }

  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <p className="text-sm font-medium text-slate-800">Riepilogo {selectedDay}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <span className={todayBadgeMuted}>Eleggibili: {summary.eligible_count}</span>
        <span className={todayBadgeMuted}>Da giocare: {summary.upcoming_count}</span>
        <span className={todayBadgeMuted}>Live: {summary.live_count}</span>
        <span className={todayBadgeMuted}>Concluse: {summary.finished_count}</span>
        <span className={todayBadgeMuted}>Escluse: {summary.excluded_count}</span>
      </div>
    </section>
  )
}
