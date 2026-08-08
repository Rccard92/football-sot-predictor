import type { CecchinoTodayScanJobResultSummary } from '../../lib/cecchinoTodayApi'
import {
  formatBookCoveragePct,
  getScanJobBookCoverage,
} from '../../lib/cecchinoTodayApi'

type Props = {
  summary: CecchinoTodayScanJobResultSummary | null | undefined
  /** Mostra policy + version (riepilogo scan finale). */
  showPolicyMeta?: boolean
  className?: string
}

/**
 * Panoramica diagnostica coverage quote Book (selection canoniche).
 * Non altera policy/selezione: solo monitoring UI.
 */
export function CecchinoTodayBookCoveragePanel({
  summary,
  showPolicyMeta = false,
  className = '',
}: Props) {
  const cov = getScanJobBookCoverage(summary)
  const coverageLabel = formatBookCoveragePct(cov.coveragePct)

  return (
    <div
      className={`mt-3 grid gap-1 rounded-lg border border-white/60 bg-white/50 p-3 text-xs text-slate-700 ${className}`}
      data-testid="cecchino-book-coverage-panel"
    >
      <p className="font-medium text-slate-800">
        Copertura selection Book — fixture arrivate alla fase KPI
      </p>
      <p className="text-[11px] text-slate-500">
        Conteggio selection canoniche Book (una volta per fixture stats-qualified)
      </p>

      {!cov.hasQuoteData ? (
        <p className="mt-1 text-slate-500" data-testid="book-coverage-waiting">
          In attesa del controllo quote
        </p>
      ) : (
        <dl className="mt-1 grid grid-cols-1 gap-1 sm:grid-cols-2">
          <div className="flex items-baseline justify-between gap-2 sm:col-span-1">
            <dt className="text-slate-600">Betfair primario</dt>
            <dd
              className="font-medium tabular-nums text-slate-800"
              data-testid="book-coverage-betfair"
            >
              {cov.betfairPrimarySelectionCount}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-amber-800/90">Bet365 fallback</dt>
            <dd
              className="font-medium tabular-nums text-amber-900"
              data-testid="book-coverage-bet365"
            >
              {cov.bet365FallbackSelectionCount}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <dt className={cov.missingSelectionCount > 0 ? 'text-red-700' : 'text-slate-600'}>
              Non recuperate
            </dt>
            <dd
              className={`font-medium tabular-nums ${
                cov.missingSelectionCount > 0 ? 'text-red-700' : 'text-slate-700'
              }`}
              data-testid="book-coverage-missing"
            >
              {cov.missingSelectionCount}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-emerald-800">Coverage</dt>
            <dd
              className="font-medium tabular-nums text-emerald-800"
              data-testid="book-coverage-pct"
            >
              {coverageLabel ?? '—'}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-2 sm:col-span-2">
            <dt className="text-slate-600">Fixture con fallback</dt>
            <dd
              className="font-medium tabular-nums text-slate-800"
              data-testid="book-coverage-fixture-fallback"
            >
              {cov.bet365FallbackFixtureCount}
            </dd>
          </div>
          {cov.bookCoverageFixtureCount > 0 ? (
            <div className="flex items-baseline justify-between gap-2 sm:col-span-2">
              <dt className="text-slate-600">Fixture in coverage</dt>
              <dd
                className="font-medium tabular-nums text-slate-800"
                data-testid="book-coverage-fixture-count"
              >
                {cov.bookCoverageFixtureCount}
              </dd>
            </div>
          ) : null}
        </dl>
      )}

      {showPolicyMeta ? (
        <div className="mt-2 space-y-0.5 border-t border-slate-200/80 pt-2 text-[11px] text-slate-500">
          <p data-testid="book-coverage-policy">
            Policy: Betfair primario · Bet365 fallback
          </p>
          <p data-testid="book-coverage-version">
            Version:{' '}
            {cov.policyVersion || 'betfair_primary_bet365_fallback_v1'}
          </p>
        </div>
      ) : null}
    </div>
  )
}
