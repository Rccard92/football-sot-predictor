import { BET_BUILDER_RESULTS_START_DATE } from '../../lib/cecchinoBetBuilderApi'
import { bbMuted } from './betBuilderStyles'
import { BetBuilderViewSwitch } from './BetBuilderViewSwitch'
import type { BetBuilderPageView } from './betBuilderResultsUtils'
import {
  formatDisplayDateIt,
  formatUpdatedTimeShort,
  isScanRunning,
  shiftIsoDate,
} from './betBuilderUtils'

type Props = {
  date: string
  onDateChange: (next: string) => void
  view: BetBuilderPageView
  onViewChange: (view: BetBuilderPageView) => void
  sourceScanStatus?: string | null
  lastUpdatedIso?: string | null
  freshnessWarning?: string | null
  fixturesEligible?: number
  fixturesWithOpportunity?: number
  opportunitiesTotal?: number
  /** Nasconde il date-nav pre-match quando Results gestisce il proprio periodo. */
  hideDateNav?: boolean
}

export function BetBuilderHeader({
  date,
  onDateChange,
  view,
  onViewChange,
  sourceScanStatus,
  lastUpdatedIso,
  freshnessWarning,
  fixturesEligible,
  fixturesWithOpportunity,
  opportunitiesTotal,
  hideDateNav = false,
}: Props) {
  const running = isScanRunning(sourceScanStatus)
  const updated = formatUpdatedTimeShort(lastUpdatedIso)
  const displayDate = formatDisplayDateIt(date)
  const isResults = view === 'results'

  const countsLine =
    !isResults &&
    (fixturesEligible != null ||
      fixturesWithOpportunity != null ||
      opportunitiesTotal != null) ? (
      <p className={`${bbMuted} text-xs sm:text-sm`}>
        {fixturesEligible != null ? (
          <span className="tabular-nums">{fixturesEligible} fixture eleggibili</span>
        ) : null}
        {fixturesWithOpportunity != null ? (
          <>
            {fixturesEligible != null ? ' · ' : null}
            <span className="tabular-nums">
              {fixturesWithOpportunity} partite con opportunity
            </span>
          </>
        ) : null}
        {opportunitiesTotal != null ? (
          <>
            {' · '}
            <span className="tabular-nums">{opportunitiesTotal} opportunity</span>
          </>
        ) : null}
      </p>
    ) : null

  return (
    <header className="space-y-3" data-testid="bet-builder-header">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <div className="min-w-0 space-y-1">
          <h1 className="text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">
            Bet Builder
          </h1>
          {isResults ? (
            <>
              <p
                className="text-sm font-medium text-slate-700"
                data-testid="bet-builder-results-subtitle"
              >
                Monitoraggio risultati
              </p>
              <p className="text-xs text-slate-500" data-testid="bet-builder-results-microcopy">
                Esito della predizione principale generata dal Bet Builder.
              </p>
              <p className="text-[11px] text-slate-400" data-testid="bet-builder-results-available-from">
                Disponibile dall&apos;08/08/2026
              </p>
            </>
          ) : (
            <>
              <p
                className="text-sm font-medium capitalize text-slate-600 sm:hidden"
                data-testid="bet-builder-date-mobile"
              >
                {displayDate}
              </p>
              {countsLine}
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:flex-col sm:items-end sm:gap-2">
          <BetBuilderViewSwitch view={view} onChange={onViewChange} />

          {!hideDateNav && !isResults ? (
            <>
              <div
                className="inline-flex items-stretch overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
                role="group"
                aria-label="Selezione giorno"
                data-testid="bet-builder-date-nav"
              >
                <button
                  type="button"
                  className="inline-flex min-h-10 min-w-10 items-center justify-center border-r border-slate-200 text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-400"
                  aria-label="Giorno precedente"
                  data-testid="bet-builder-date-prev"
                  onClick={() => onDateChange(shiftIsoDate(date, -1))}
                >
                  ←
                </button>
                <label className="relative flex min-h-10 min-w-[9.5rem] flex-1 cursor-pointer items-center justify-center px-2 sm:min-w-[11.5rem]">
                  <span className="sr-only">Data</span>
                  <span
                    className="pointer-events-none hidden text-sm font-semibold capitalize text-slate-900 sm:inline"
                    data-testid="bet-builder-date-label"
                    aria-hidden
                  >
                    {displayDate}
                  </span>
                  <span
                    className="pointer-events-none text-sm font-semibold text-slate-800 sm:hidden"
                    aria-hidden
                  >
                    Cambia data
                  </span>
                  <input
                    id="bet-builder-date"
                    type="date"
                    className="absolute inset-0 cursor-pointer opacity-0"
                    value={date}
                    min={undefined}
                    aria-label="Cambia data"
                    data-testid="bet-builder-date-input"
                    onChange={(e) => {
                      if (e.target.value) onDateChange(e.target.value)
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="inline-flex min-h-10 min-w-10 items-center justify-center border-l border-slate-200 text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-400"
                  aria-label="Giorno successivo"
                  data-testid="bet-builder-date-next"
                  onClick={() => onDateChange(shiftIsoDate(date, 1))}
                >
                  →
                </button>
              </div>

              <p className="text-xs text-slate-600" data-testid="bet-builder-updated-status">
                {running ? (
                  <span className="font-semibold text-slate-800">In aggiornamento</span>
                ) : (
                  <>
                    Aggiornato <span className="font-semibold text-slate-800">{updated}</span>
                  </>
                )}
              </p>
              {freshnessWarning ? (
                <p className="max-w-xs text-xs text-amber-800 sm:text-right" role="status">
                  Avviso freschezza: {freshnessWarning}
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      </div>

      {isResults ? (
        <p className="sr-only">
          Monitoraggio disponibile dal {BET_BUILDER_RESULTS_START_DATE}
        </p>
      ) : null}

      {running && !isResults ? (
        <div
          className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-950"
          role="status"
          data-testid="scan-running-banner"
        >
          Aggiornamento Cecchino in corso
        </div>
      ) : null}
    </header>
  )
}
