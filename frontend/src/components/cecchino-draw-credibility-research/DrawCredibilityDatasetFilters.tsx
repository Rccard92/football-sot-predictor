import {
  DRAW_CREDIBILITY_COHORT_LABELS,
  type DrawCredibilityCohort,
} from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  dateFrom: string
  dateTo: string
  competitionId: string
  cohort: DrawCredibilityCohort
  pageSize: number
  loading: boolean
  exporting: boolean
  onDateFromChange: (v: string) => void
  onDateToChange: (v: string) => void
  onCompetitionIdChange: (v: string) => void
  onCohortChange: (v: DrawCredibilityCohort) => void
  onPageSizeChange: (v: number) => void
  onLoadDataset: () => void
  onExportCsv: () => void
}

function Spinner() {
  return (
    <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
  )
}

export function DrawCredibilityDatasetFilters({
  dateFrom,
  dateTo,
  competitionId,
  cohort,
  pageSize,
  loading,
  exporting,
  onDateFromChange,
  onDateToChange,
  onCompetitionIdChange,
  onCohortChange,
  onPageSizeChange,
  onLoadDataset,
  onExportCsv,
}: Props) {
  const inputClass =
    'mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm shadow-sm transition-shadow focus:border-violet-300 focus:outline-none focus:ring-2 focus:ring-violet-100'

  return (
    <section className="sticky top-0 z-20 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm backdrop-blur-sm">
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
        <label className="text-xs font-medium text-slate-600">
          Data da
          <input
            type="date"
            className={inputClass}
            value={dateFrom}
            onChange={(e) => onDateFromChange(e.target.value)}
          />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Data a
          <input
            type="date"
            className={inputClass}
            value={dateTo}
            onChange={(e) => onDateToChange(e.target.value)}
          />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Competition ID
          <input
            type="number"
            min={1}
            className={inputClass}
            value={competitionId}
            onChange={(e) => onCompetitionIdChange(e.target.value)}
            placeholder="opzionale"
          />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Coorte
          <select
            className={inputClass}
            value={cohort}
            onChange={(e) => onCohortChange(e.target.value as DrawCredibilityCohort)}
          >
            {(Object.entries(DRAW_CREDIBILITY_COHORT_LABELS) as Array<[DrawCredibilityCohort, string]>).map(
              ([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ),
            )}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Righe per pagina
          <select
            className={inputClass}
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
          >
            {[50, 100, 200, 500].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={loading}
          onClick={onLoadDataset}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
        >
          {loading ? <Spinner /> : null}
          Carica dataset
        </button>
        <button
          type="button"
          disabled={exporting || loading}
          onClick={onExportCsv}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
        >
          {exporting ? <Spinner /> : null}
          Esporta CSV
        </button>
      </div>
    </section>
  )
}
