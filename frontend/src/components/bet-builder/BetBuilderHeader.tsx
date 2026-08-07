import { bbCard, bbCardPadding, bbChipIdle, bbInput, bbMuted } from './betBuilderStyles'
import { formatUpdatedAt, isScanRunning, shiftIsoDate } from './betBuilderUtils'

type Props = {
  date: string
  onDateChange: (next: string) => void
  sourceScanStatus?: string | null
  lastUpdatedIso?: string | null
  freshnessWarning?: string | null
  revisionUpdatedBanner?: boolean
}

export function BetBuilderHeader({
  date,
  onDateChange,
  sourceScanStatus,
  lastUpdatedIso,
  freshnessWarning,
  revisionUpdatedBanner,
}: Props) {
  const running = isScanRunning(sourceScanStatus)

  return (
    <header className="space-y-4">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
          Bet Builder
        </h1>
        <p className={`${bbMuted} max-w-3xl`}>
          Opportunity generate dai dati Cecchino Today. Quota, Segnali e Acquistabilità restano
          evidenze distinte.
        </p>
      </div>

      <div className={`${bbCard} ${bbCardPadding} flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between`}>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Selezione giorno">
          <button
            type="button"
            className={`${bbChipIdle} min-w-11 justify-center`}
            aria-label="Giorno precedente"
            onClick={() => onDateChange(shiftIsoDate(date, -1))}
          >
            ‹
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
            ›
          </button>
        </div>

        <div className="space-y-1 text-sm text-slate-600">
          <p>
            Stato sorgente:{' '}
            <span className="font-semibold text-slate-800">
              {sourceScanStatus ?? 'n/d'}
            </span>
          </p>
          <p>
            Ultimo aggiornamento:{' '}
            <span className="font-semibold tabular-nums text-slate-800">
              {formatUpdatedAt(lastUpdatedIso)}
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

      {revisionUpdatedBanner ? (
        <div
          className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-950"
          role="status"
          data-testid="revision-updated-banner"
        >
          Dati aggiornati dalla nuova scansione Cecchino
        </div>
      ) : null}
    </header>
  )
}
