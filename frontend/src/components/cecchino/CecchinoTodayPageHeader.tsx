type Props = {
  isScanned: boolean
  scanDayLoading: boolean
  scanInProgress?: boolean
  updateResultsLoading: boolean
  revalidateLoading?: boolean
  recomputeLoading?: boolean
  selectedFixtureId?: number | null
  refreshBetfairLoading?: boolean
  onScanDay: (forceRescan: boolean) => void
  onUpdateResults: () => void
  onRevalidateDay?: () => void
  onRecomputeCecchino?: () => void
  onRefreshBetfairOdds?: () => void
}

export function CecchinoTodayPageHeader({
  isScanned,
  scanDayLoading,
  scanInProgress = false,
  updateResultsLoading,
  revalidateLoading = false,
  recomputeLoading = false,
  selectedFixtureId = null,
  refreshBetfairLoading = false,
  onScanDay,
  onUpdateResults,
  onRevalidateDay,
  onRecomputeCecchino,
  onRefreshBetfairOdds,
}: Props) {
  const scanBusy = scanDayLoading || scanInProgress

  return (
    <header className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Cecchino Today
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Dashboard giornaliera partite eleggibili — timeline, filtri e risultati finali.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        {!isScanned ? (
          <button
            type="button"
            onClick={() => onScanDay(false)}
            disabled={scanBusy}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {scanBusy ? 'Scansione in corso…' : 'Avvia scansione giornata'}
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => onUpdateResults()}
              disabled={updateResultsLoading || scanBusy}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {updateResultsLoading ? 'Aggiornamento…' : 'Aggiorna risultati giornata'}
            </button>
            <button
              type="button"
              onClick={() => onScanDay(true)}
              disabled={scanBusy}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {scanBusy ? 'Scansione in corso…' : 'Riscansiona giornata'}
            </button>
            {onRevalidateDay && (
              <button
                type="button"
                onClick={() => onRevalidateDay()}
                disabled={revalidateLoading || scanBusy}
                className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-5 py-2.5 text-sm font-semibold text-indigo-900 shadow-sm transition hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {revalidateLoading ? 'Rivalidazione…' : 'Rivalida eleggibilità'}
              </button>
            )}
            {onRecomputeCecchino && (
              <button
                type="button"
                onClick={() => onRecomputeCecchino()}
                disabled={recomputeLoading || scanBusy}
                className="inline-flex items-center gap-2 rounded-lg border border-violet-300 bg-violet-50 px-5 py-2.5 text-sm font-semibold text-violet-900 shadow-sm transition hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {recomputeLoading ? 'Ricalcolo…' : 'Ricalcola Cecchino con nuovi pesi'}
              </button>
            )}
            {selectedFixtureId != null && onRefreshBetfairOdds && (
              <button
                type="button"
                onClick={() => onRefreshBetfairOdds()}
                disabled={refreshBetfairLoading || scanBusy}
                className="inline-flex items-center gap-2 rounded-lg border border-emerald-300 bg-emerald-50 px-5 py-2.5 text-sm font-semibold text-emerald-900 shadow-sm transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {refreshBetfairLoading ? 'Aggiornamento…' : 'Aggiorna quote Betfair'}
              </button>
            )}
          </>
        )}
      </div>
    </header>
  )
}
