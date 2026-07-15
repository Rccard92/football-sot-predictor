type Props = {
  dateFrom: string
  dateTo: string
  competitionId: string
  onlyEligible: boolean
  loading: boolean
  onDateFromChange: (v: string) => void
  onDateToChange: (v: string) => void
  onCompetitionIdChange: (v: string) => void
  onOnlyEligibleChange: (v: boolean) => void
  onRunAudit: () => void
}

function Spinner() {
  return (
    <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
  )
}

export function DrawCredibilityResearchFilters({
  dateFrom,
  dateTo,
  competitionId,
  onlyEligible,
  loading,
  onDateFromChange,
  onDateToChange,
  onCompetitionIdChange,
  onOnlyEligibleChange,
  onRunAudit,
}: Props) {
  const inputClass =
    'mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm shadow-sm transition-shadow focus:border-violet-300 focus:outline-none focus:ring-2 focus:ring-violet-100'

  return (
    <section className="sticky top-0 z-20 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm backdrop-blur-sm">
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
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
        <label className="flex items-end gap-2 pb-2 text-xs font-medium text-slate-600">
          <input
            type="checkbox"
            checked={onlyEligible}
            onChange={(e) => onOnlyEligibleChange(e.target.checked)}
            className="rounded border-slate-300 text-violet-600 focus:ring-violet-200"
          />
          Solo fixture eleggibili
        </label>
      </div>
      <div className="mt-4">
        <button
          type="button"
          disabled={loading}
          onClick={onRunAudit}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
        >
          {loading ? <Spinner /> : null}
          Esegui audit
        </button>
      </div>
    </section>
  )
}
