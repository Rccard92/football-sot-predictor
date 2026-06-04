import { todayCard, todayCardPadding } from './cecchinoTodayStyles'

type Props = {
  scanDate: string
  onScanDateChange: (date: string) => void
  onScan: () => void
  scanLoading: boolean
}

export function CecchinoTodayPageHeader({
  scanDate,
  onScanDateChange,
  onScan,
  scanLoading,
}: Props) {
  return (
    <header className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Cecchino Today
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Discovery giornaliera — solo partite eleggibili con quote complete, statistiche OK e
          nessun leakage.
        </p>
      </div>

      <div className={`${todayCard} ${todayCardPadding} flex flex-wrap items-end gap-4`}>
        <label className="flex min-w-[160px] flex-col gap-1.5 text-sm font-medium text-slate-700">
          Data scan
          <input
            type="date"
            value={scanDate}
            onChange={(e) => onScanDateChange(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          />
        </label>
        <button
          type="button"
          onClick={onScan}
          disabled={scanLoading}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {scanLoading && (
            <span
              className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
              aria-hidden
            />
          )}
          {scanLoading ? 'Scansione in corso…' : 'Aggiorna partite odierne'}
        </button>
      </div>
    </header>
  )
}
