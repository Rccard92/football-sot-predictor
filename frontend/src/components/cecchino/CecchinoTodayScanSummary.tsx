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
  const rs = (report as CecchinoTodayScanReport & { result_summary?: Record<string, unknown> })
    .result_summary
  const funnel = (rs?.excluded_funnel ?? {}) as Record<string, number>
  const excludedQuote = countExcluded(report, [
    'excluded_missing_bookmaker',
    'excluded_missing_1x2_market',
  ])
  const excludedStats = countExcluded(report, [
    'excluded_insufficient_stats',
    'excluded_leakage_failed',
  ])
  const excludedCompetition = countExcluded(report, [
    'excluded_cup',
    'excluded_women',
    'excluded_friendly',
    'excluded_youth',
    'excluded_started',
  ])
  const excludedCecchino = countExcluded(report, [
    'excluded_missing_picchetto',
    'excluded_zero_probability',
    'excluded_cecchino_not_calculable',
    'excluded_kpi_not_calculable',
  ])
  const excludedErrors = countExcluded(report, ['excluded_mapping_error', 'error'])
  const found = report.fixtures_found ?? report.total_discovered

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

      <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3 text-xs text-slate-700">
        <p className="mb-2 font-medium text-slate-800">Funnel esclusioni</p>
        <ul className="space-y-1">
          <li>Fixture trovate: {found}</li>
          <li>
            Dopo filtro competizione:{' '}
            {Number(rs?.fixtures_after_competition_gate ?? rs?.after_competition_filter ?? '—')}
          </li>
          <li>
            Dopo gate bookmaker: {Number(rs?.fixtures_after_bookmaker_gate ?? '—')}
          </li>
          <li>Dopo gate stats: {Number(rs?.fixtures_after_stats_gate ?? '—')}</li>
          <li className="font-medium text-emerald-800">Eleggibili finali: {report.eligible}</li>
        </ul>
      </div>

      <div className="flex flex-wrap gap-2">
        <span className={todayBadgeMuted}>Trovate: {found}</span>
        <span className={todayBadgeOk}>Eleggibili: {report.eligible}</span>
        {(funnel.competition ?? excludedCompetition) > 0 && (
          <span className={todayBadgeMuted}>
            Escluse competizione: {funnel.competition ?? excludedCompetition}
          </span>
        )}
        {(funnel.bookmaker ?? countExcluded(report, ['excluded_missing_bookmaker'])) > 0 && (
          <span className={todayBadgeMuted}>
            Escluse bookmaker: {funnel.bookmaker ?? countExcluded(report, ['excluded_missing_bookmaker'])}
          </span>
        )}
        {(funnel.market_1x2 ?? countExcluded(report, ['excluded_missing_1x2_market'])) > 0 && (
          <span className={todayBadgeMuted}>
            Escluse mercato 1X2: {funnel.market_1x2 ?? countExcluded(report, ['excluded_missing_1x2_market'])}
          </span>
        )}
        {(funnel.stats ?? excludedStats) > 0 && (
          <span className={todayBadgeMuted}>Escluse stats: {funnel.stats ?? excludedStats}</span>
        )}
        {(funnel.cecchino ?? excludedCecchino) > 0 && (
          <span className={todayBadgeMuted}>Escluse Cecchino: {funnel.cecchino ?? excludedCecchino}</span>
        )}
        {excludedQuote > 0 && (
          <span className={todayBadgeMuted}>Escluse quote (tot): {excludedQuote}</span>
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
