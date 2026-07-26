import type {
  CecchinoTodayEligibilityTransitions,
  CecchinoTodayScanReport,
} from '../../lib/cecchinoTodayApi'
import { todayBadgeActive, todayBadgeMuted, todayBadgeOk, todayCard, todayCardPadding } from './cecchinoTodayStyles'

type Props = {
  report: CecchinoTodayScanReport
  onShowExcluded?: () => void
}

function countExcluded(report: CecchinoTodayScanReport, keys: string[]): number {
  const ex = report.excluded || {}
  return keys.reduce((sum, k) => sum + (ex[k] ?? 0), 0)
}

function formatTargetDate(iso: string | undefined): string | null {
  if (!iso) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return iso
  return `${m[3]}/${m[2]}/${m[1]}`
}

const TRANSITION_BADGES: { key: keyof CecchinoTodayEligibilityTransitions; label: string }[] = [
  { key: 'new_eligible', label: 'Nuove eleggibili' },
  { key: 'promoted_to_eligible', label: 'Promosse a eleggibili' },
  { key: 'eligible_refreshed', label: 'Eleggibili aggiornate' },
  { key: 'eligible_preserved_refresh_failed', label: 'Eleggibili preservate' },
  { key: 'eligible_frozen_after_kickoff', label: 'Congelate dopo il kickoff' },
  { key: 'eligible_preserved_terminal_status', label: 'Stati terminali preservati' },
  { key: 'started_never_eligible', label: 'Iniziate mai eleggibili' },
]

export function CecchinoTodayScanSummary({ report, onShowExcluded }: Props) {
  const rs = (report as CecchinoTodayScanReport & { result_summary?: Record<string, unknown> })
    .result_summary
  const funnel = (rs?.excluded_funnel ?? {}) as Record<string, number>
  const transitions = (rs?.eligibility_transitions ?? {}) as CecchinoTodayEligibilityTransitions
  const autoScan = (rs?.auto_scan ?? null) as
    | {
        execution_source?: string
        execution_mode?: string
        execution_slot?: string
        target_date?: string
        attempt?: number
      }
    | null
  const protectionActive =
    rs?.snapshot_eligible_protection_active === true ||
    typeof rs?.protected_eligible_total === 'number' ||
    Object.keys(transitions).length > 0
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
  const targetLabel = formatTargetDate(autoScan?.target_date)

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
        {autoScan && autoScan.execution_source === 'auto_scan' ? (
          <>
            <span className={todayBadgeActive}>Origine: Automatica</span>
            {autoScan.execution_mode === 'synchronous' ? (
              <span className={todayBadgeMuted}>Modalità: Sincrona</span>
            ) : null}
            {autoScan.execution_slot === 'recovery' ? (
              <span className={todayBadgeMuted}>Slot: Recupero</span>
            ) : autoScan.execution_slot === 'primary' ? (
              <span className={todayBadgeMuted}>Slot: Principale</span>
            ) : null}
            {targetLabel ? <span className={todayBadgeMuted}>Target: {targetLabel}</span> : null}
            {typeof autoScan.attempt === 'number' ? (
              <span className={todayBadgeMuted}>Tentativo: {autoScan.attempt}</span>
            ) : null}
          </>
        ) : null}
        <span className={todayBadgeMuted}>Trovate: {found}</span>
        <span className={todayBadgeOk}>Eleggibili: {report.eligible}</span>
        {TRANSITION_BADGES.map(({ key, label }) => {
          const count = Number(transitions[key] ?? 0)
          if (count <= 0) return null
          return (
            <span key={key} className={todayBadgeOk}>
              {label}: {count}
            </span>
          )
        })}
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
        {protectionActive && (
          <span className={todayBadgeActive}>Protezione snapshot eligible: attiva</span>
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
