type Props = {
  isScanned: boolean
  scanDayLoading: boolean
  scanInProgress?: boolean
  updateResultsLoading: boolean
  revalidateLoading?: boolean
  recomputeLoading?: boolean
  selectedFixtureId?: number | null
  refreshBetfairLoading?: boolean
  dailyAuditExportLoading?: boolean
  dailyAuditExportError?: string | null
  dailyV35AuditExportLoading?: boolean
  dailyV35AuditExportError?: string | null
  v35AnalysisExportLoading?: boolean
  v35AnalysisExportError?: string | null
  onScanDay: (forceRescan: boolean) => void
  onUpdateResults: () => void
  onRevalidateDay?: () => void
  onRecomputeCecchino?: () => void
  onRefreshBetfairOdds?: () => void
  onDownloadDailyAudit?: () => void
  onDownloadDailyV35Audit?: () => void
  onDownloadV35Analysis?: () => void
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
  dailyAuditExportLoading = false,
  dailyAuditExportError = null,
  dailyV35AuditExportLoading = false,
  dailyV35AuditExportError = null,
  v35AnalysisExportLoading = false,
  v35AnalysisExportError = null,
  onScanDay,
  onUpdateResults,
  onRevalidateDay,
  onRecomputeCecchino,
  onRefreshBetfairOdds,
  onDownloadDailyAudit,
  onDownloadDailyV35Audit,
  onDownloadV35Analysis,
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
            {onDownloadDailyAudit && (
              <button
                type="button"
                data-testid="daily-purch-audit-download-btn"
                onClick={() => onDownloadDailyAudit()}
                disabled={dailyAuditExportLoading || scanBusy}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {dailyAuditExportLoading ? 'Preparazione…' : 'Scarica audit giornata'}
              </button>
            )}
            {onDownloadDailyV35Audit && (
              <button
                type="button"
                data-testid="daily-v35-purch-audit-download-btn"
                onClick={() => onDownloadDailyV35Audit()}
                disabled={dailyV35AuditExportLoading || scanBusy}
                className="inline-flex items-center gap-2 rounded-lg border border-violet-200 bg-violet-50 px-5 py-2.5 text-sm font-semibold text-violet-900 shadow-sm transition hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {dailyV35AuditExportLoading ? 'Preparazione…' : (
                  <>
                    Scarica audit V3.5 giornata
                    <span className="text-[10px] font-bold uppercase tracking-wide opacity-80">SHADOW</span>
                  </>
                )}
              </button>
            )}
            {onDownloadV35Analysis && (
              <button
                type="button"
                data-testid="v35-analysis-export-btn"
                onClick={() => onDownloadV35Analysis()}
                disabled={v35AnalysisExportLoading || scanBusy}
                className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-5 py-2.5 text-sm font-semibold text-amber-950 shadow-sm transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {v35AnalysisExportLoading ? 'Preparazione…' : (
                  <>
                    Scarica dataset V3.5 test 20–26/08
                    <span className="text-[10px] font-bold uppercase tracking-wide opacity-80">ANALYSIS</span>
                  </>
                )}
              </button>
            )}
            {dailyAuditExportError ? (
              <p className="w-full text-sm text-red-700" data-testid="daily-purch-audit-export-error">
                {dailyAuditExportError}
              </p>
            ) : null}
            {dailyV35AuditExportError ? (
              <p className="w-full text-sm text-red-700" data-testid="daily-v35-purch-audit-export-error">
                {dailyV35AuditExportError}
              </p>
            ) : null}
            {v35AnalysisExportError ? (
              <p className="w-full text-sm text-red-700" data-testid="v35-analysis-export-error">
                {v35AnalysisExportError}
              </p>
            ) : null}
            {selectedFixtureId != null && onRefreshBetfairOdds && (
              <button
                type="button"
                onClick={() => onRefreshBetfairOdds()}
                disabled={refreshBetfairLoading || scanBusy}
                className="inline-flex items-center gap-2 rounded-lg border border-emerald-300 bg-emerald-50 px-5 py-2.5 text-sm font-semibold text-emerald-900 shadow-sm transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {refreshBetfairLoading ? 'Aggiornamento…' : 'Aggiorna quote Book'}
              </button>
            )}
          </>
        )}
      </div>
    </header>
  )
}
