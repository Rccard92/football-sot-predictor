type Props = {
  dateFrom: string
  dateTo: string
  competitionId: string
  binCount: number
  minGroupSize: number
  bootstrapIterations: number
  loading: boolean
  onDateFromChange: (v: string) => void
  onDateToChange: (v: string) => void
  onCompetitionIdChange: (v: string) => void
  onBinCountChange: (v: number) => void
  onMinGroupSizeChange: (v: number) => void
  onBootstrapIterationsChange: (v: number) => void
  onRunAnalysis: () => void
}

export function DrawCredibilityStatisticsFilters({
  dateFrom,
  dateTo,
  competitionId,
  binCount,
  minGroupSize,
  bootstrapIterations,
  loading,
  onDateFromChange,
  onDateToChange,
  onCompetitionIdChange,
  onBinCountChange,
  onMinGroupSizeChange,
  onBootstrapIterationsChange,
  onRunAnalysis,
}: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Filtri analisi statistica</h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block text-xs text-slate-600">
          Da
          <input
            type="date"
            className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            value={dateFrom}
            onChange={(e) => onDateFromChange(e.target.value)}
          />
        </label>
        <label className="block text-xs text-slate-600">
          A
          <input
            type="date"
            className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            value={dateTo}
            onChange={(e) => onDateToChange(e.target.value)}
          />
        </label>
        <label className="block text-xs text-slate-600">
          Competition ID
          <input
            type="text"
            className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            value={competitionId}
            placeholder="opzionale"
            onChange={(e) => onCompetitionIdChange(e.target.value)}
          />
        </label>
        <label className="block text-xs text-slate-600">
          Bin quantili
          <input
            type="number"
            min={3}
            max={10}
            className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            value={binCount}
            onChange={(e) => onBinCountChange(Number(e.target.value))}
          />
        </label>
        <label className="block text-xs text-slate-600">
          Min gruppo
          <input
            type="number"
            min={10}
            max={100}
            className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            value={minGroupSize}
            onChange={(e) => onMinGroupSizeChange(Number(e.target.value))}
          />
        </label>
        <label className="block text-xs text-slate-600">
          Bootstrap iter.
          <input
            type="number"
            min={100}
            max={2000}
            step={100}
            className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            value={bootstrapIterations}
            onChange={(e) => onBootstrapIterationsChange(Number(e.target.value))}
          />
        </label>
      </div>
      <div className="mt-4">
        <button
          type="button"
          disabled={loading}
          className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
          onClick={onRunAnalysis}
        >
          {loading ? 'Analisi in corso…' : 'Esegui analisi'}
        </button>
      </div>
    </section>
  )
}
