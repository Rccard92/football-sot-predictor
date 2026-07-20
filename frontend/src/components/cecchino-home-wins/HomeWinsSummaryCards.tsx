import type { HomeWinsSummary } from '../../lib/cecchinoHomeWinsApi'
import { todayCard, todayCardPadding } from '../cecchino/cecchinoTodayStyles'

type Props = {
  summary: HomeWinsSummary | null
  loading?: boolean
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">{value}</p>
    </div>
  )
}

export function HomeWinsSummaryCards({ summary, loading }: Props) {
  if (loading && !summary) {
    return (
      <div className={`${todayCard} ${todayCardPadding}`}>
        <p className="text-sm text-slate-500">Caricamento riepilogo…</p>
      </div>
    )
  }
  if (!summary) return null
  const range =
    summary.scan_date_min && summary.scan_date_max
      ? `${summary.scan_date_min} → ${summary.scan_date_max}`
      : '—'
  return (
    <div className={`${todayCard} ${todayCardPadding}`}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
        <Stat label="Vittorie casalinghe" value={summary.total_home_wins} />
        <Stat label="Completi" value={summary.complete} />
        <Stat label="Parziali" value={summary.partial} />
        <Stat label="Competizioni" value={summary.competitions_count} />
        <Stat label="Intervallo storico" value={range} />
        <Stat label="% KPI" value={`${summary.pct_with_kpi}%`} />
        <Stat label="% Balance" value={`${summary.pct_with_balance}%`} />
        <Stat label="% Intensità Goal v5" value={`${summary.pct_with_goal_intensity_v5}%`} />
      </div>
    </div>
  )
}
