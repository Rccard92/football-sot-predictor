import type { CecchinoTodayScanReport } from '../../lib/cecchinoTodayApi'
import { todayBadgeActive, todayBadgeMuted, todayBadgeOk, todayCard, todayCardPadding } from './cecchinoTodayStyles'

type Props = {
  report: CecchinoTodayScanReport
  onShowExcluded?: () => void
}

function countExcluded(report: CecchinoTodayScanReport, keys: string[]): number {
  const ex = report.excluded || {}
  return keys.reduce((sum, k) => sum + (ex[k] ?? 0), 0)
}

export function CecchinoTodayScanSummary({ report, onShowExcluded }: Props) {
  const excludedQuote = countExcluded(report, [
    'excluded_missing_bookmaker',
    'excluded_missing_1x2_market',
  ])
  const excludedStats = countExcluded(report, ['excluded_insufficient_stats'])
  const excludedCompetition = countExcluded(report, [
    'excluded_cup',
    'excluded_women',
    'excluded_friendly',
    'excluded_youth',
    'excluded_started',
  ])
  const excludedErrors = countExcluded(report, ['excluded_mapping_error', 'error'])

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-3`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-slate-800">Riepilogo scan — {report.scan_date}</p>
        {onShowExcluded && (
          <button
            type="button"
            onClick={onShowExcluded}
            className="text-sm font-medium text-blue-600 hover:text-blue-800"
          >
            Vedi escluse
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <span className={todayBadgeMuted}>
          Trovate: {report.fixtures_found ?? report.total_discovered}
        </span>
        <span className={todayBadgeOk}>Eleggibili: {report.eligible}</span>
        {excludedQuote > 0 && (
          <span className={todayBadgeMuted}>Escluse quote: {excludedQuote}</span>
        )}
        {excludedStats > 0 && (
          <span className={todayBadgeMuted}>Escluse statistiche: {excludedStats}</span>
        )}
        {excludedCompetition > 0 && (
          <span className={todayBadgeMuted}>Escluse competizione: {excludedCompetition}</span>
        )}
        {excludedErrors > 0 && (
          <span className={todayBadgeMuted}>Errori: {excludedErrors}</span>
        )}
        <span className={todayBadgeActive}>Data: {report.scan_date}</span>
      </div>
      {(report.top_exclusion_reasons?.length ?? 0) > 0 && (
        <ul className="text-xs text-slate-600">
          {report.top_exclusion_reasons!.slice(0, 5).map((r) => (
            <li key={r.status}>
              {r.status}: {r.count}
            </li>
          ))}
        </ul>
      )}
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
