type Props = {
  dateFrom: string
  dateTo: string
  competitionId: string
  finalHoldoutPct: number
  innerSplits: number
  bootstrapIterations: number
  loading: boolean
  onDateFromChange: (v: string) => void
  onDateToChange: (v: string) => void
  onCompetitionIdChange: (v: string) => void
  onFinalHoldoutPctChange: (v: number) => void
  onInnerSplitsChange: (v: number) => void
  onBootstrapIterationsChange: (v: number) => void
  onRunComparison: () => void
}

export function DrawCredibilityModelComparisonFilters({
  dateFrom,
  dateTo,
  competitionId,
  finalHoldoutPct,
  innerSplits,
  bootstrapIterations,
  loading,
  onDateFromChange,
  onDateToChange,
  onCompetitionIdChange,
  onFinalHoldoutPctChange,
  onInnerSplitsChange,
  onBootstrapIterationsChange,
  onRunComparison,
}: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Filtri confronto modelli 1D</h3>
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
          Final holdout %
          <input
            type="number"
            min={0.2}
            max={0.35}
            step={0.01}
            className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            value={finalHoldoutPct}
            onChange={(e) => onFinalHoldoutPctChange(Number(e.target.value))}
          />
        </label>
        <label className="block text-xs text-slate-600">
          Inner split
          <input
            type="number"
            min={2}
            max={5}
            className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            value={innerSplits}
            onChange={(e) => onInnerSplitsChange(Number(e.target.value))}
          />
        </label>
        <label className="block text-xs text-slate-600">
          Bootstrap iterations
          <input
            type="number"
            min={100}
            max={2000}
            step={50}
            className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            value={bootstrapIterations}
            onChange={(e) => onBootstrapIterationsChange(Number(e.target.value))}
          />
        </label>
      </div>
      <button
        type="button"
        disabled={loading}
        className="mt-4 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
        onClick={onRunComparison}
      >
        {loading ? 'Confronto in corso…' : 'Confronta modelli'}
      </button>
    </section>
  )
}
