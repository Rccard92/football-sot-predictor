import type { CecchinoTodayScanReport } from '../../lib/cecchinoTodayApi'
import { todayBadgeActive, todayBadgeMuted, todayBadgeOk, todayCard, todayCardPadding } from './cecchinoTodayStyles'

type Props = {
  report: CecchinoTodayScanReport
}

function countExcluded(report: CecchinoTodayScanReport, keys: string[]): number {
  const ex = report.excluded || {}
  return keys.reduce((sum, k) => sum + (ex[k] ?? 0), 0)
}

export function CecchinoTodayScanSummary({ report }: Props) {
  const excludedQuote = countExcluded(report, [
    'excluded_missing_bookmaker',
    'excluded_missing_1x2_market',
  ])
  const excludedStats = countExcluded(report, ['excluded_insufficient_stats'])
  const excludedOther =
    (report.excluded_total ?? Object.values(report.excluded || {}).reduce((a, b) => a + b, 0)) -
    excludedQuote -
    excludedStats

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-3`}>
      <p className="text-sm font-medium text-slate-800">Riepilogo scan</p>
      <div className="flex flex-wrap gap-2">
        <span className={todayBadgeMuted}>
          Trovate: {report.total_discovered}
        </span>
        <span className={todayBadgeOk}>
          Eleggibili: {report.eligible}
        </span>
        {excludedQuote > 0 && (
          <span className={todayBadgeMuted}>
            Escluse quote: {excludedQuote}
          </span>
        )}
        {excludedStats > 0 && (
          <span className={todayBadgeMuted}>
            Escluse statistiche: {excludedStats}
          </span>
        )}
        {excludedOther > 0 && (
          <span className={todayBadgeMuted}>
            Altre esclusioni: {excludedOther}
          </span>
        )}
        <span className={todayBadgeActive}>
          Data: {report.scan_date}
        </span>
      </div>
      {(report.warnings?.length ?? 0) > 0 && (
        <ul className="list-inside list-disc text-xs text-amber-800">
          {report.warnings!.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
