type Props = {
  onScanToday: () => void
  onScanTomorrow: () => void
  scanTodayLoading: boolean
  scanTomorrowLoading: boolean
}

export function CecchinoTodayPageHeader({
  onScanToday,
  onScanTomorrow,
  scanTodayLoading,
  scanTomorrowLoading,
}: Props) {
  return (
    <header className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Cecchino Today
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Discovery giornaliera persistente — scansiona oggi o domani e naviga tra le giornate
          salvate (storico 7 giorni).
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onScanToday}
          disabled={scanTodayLoading}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {scanTodayLoading && (
            <span
              className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
              aria-hidden
            />
          )}
          {scanTodayLoading ? 'Scansione oggi…' : 'Scansione oggi'}
        </button>
        <button
          type="button"
          onClick={onScanTomorrow}
          disabled={scanTomorrowLoading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {scanTomorrowLoading && (
            <span
              className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700"
              aria-hidden
            />
          )}
          {scanTomorrowLoading ? 'Scansione domani…' : 'Scansione domani'}
        </button>
      </div>
    </header>
  )
}
