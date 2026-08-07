import {
  bbChipIdle,
  bbInput,
  bbMuted,
} from './betBuilderStyles'
import {
  formatDisplayDateIt,
  formatUpdatedTimeShort,
  isScanRunning,
  shiftIsoDate,
} from './betBuilderUtils'

type Props = {
  date: string
  onDateChange: (next: string) => void
  sourceScanStatus?: string | null
  lastUpdatedIso?: string | null
  freshnessWarning?: string | null
  fixturesEligible?: number
  fixturesWithOpportunity?: number
  opportunitiesTotal?: number
}

export function BetBuilderHeader({
  date,
  onDateChange,
  sourceScanStatus,
  lastUpdatedIso,
  freshnessWarning,
  fixturesEligible,
  fixturesWithOpportunity,
  opportunitiesTotal,
}: Props) {
  const running = isScanRunning(sourceScanStatus)
  const updated = formatUpdatedTimeShort(lastUpdatedIso)

  return (
    <header className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Bet Builder</h1>
        <p className="text-sm font-medium capitalize text-slate-600">
          {formatDisplayDateIt(date)}
        </p>
      </div>

      {(fixturesEligible != null ||
        fixturesWithOpportunity != null ||
        opportunitiesTotal != null) && (
        <p className={`${bbMuted} text-sm`}>
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
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Selezione giorno">
          <button
            type="button"
            className={`${bbChipIdle} min-w-11 justify-center`}
            aria-label="Giorno precedente"
            onClick={() => onDateChange(shiftIsoDate(date, -1))}
          >
            ←
          </button>
          <label className="sr-only" htmlFor="bet-builder-date">
            Data
          </label>
          <input
            id="bet-builder-date"
            type="date"
            className={`${bbInput} w-auto min-w-[10.5rem]`}
            value={date}
            onChange={(e) => {
              if (e.target.value) onDateChange(e.target.value)
            }}
          />
          <button
            type="button"
            className={`${bbChipIdle} min-w-11 justify-center`}
            aria-label="Giorno successivo"
            onClick={() => onDateChange(shiftIsoDate(date, 1))}
          >
            →
          </button>
        </div>

        <div className="text-sm text-slate-600">
          <p>
            Stato:{' '}
            <span className="font-semibold text-slate-800">
              {running ? 'In aggiornamento' : `Aggiornato ${updated}`}
            </span>
          </p>
          {freshnessWarning ? (
            <p className="text-amber-800" role="status">
              Avviso freschezza: {freshnessWarning}
            </p>
          ) : null}
        </div>
      </div>

      {running ? (
        <div
          className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm font-medium text-sky-950"
          role="status"
          data-testid="scan-running-banner"
        >
          Aggiornamento Cecchino in corso
        </div>
      ) : null}
    </header>
  )
}
