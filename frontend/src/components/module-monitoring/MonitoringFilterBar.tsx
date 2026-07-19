type Props = {
  dateFrom: string
  dateTo: string
  competitionId: string
  onDateFrom: (v: string) => void
  onDateTo: (v: string) => void
  onCompetitionId: (v: string) => void
  onRefresh: () => void
  loading?: boolean
}

export function MonitoringFilterBar({
  dateFrom,
  dateTo,
  competitionId,
  onDateFrom,
  onDateTo,
  onCompetitionId,
  onRefresh,
  loading,
}: Props) {
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-slate-200/70 bg-white p-3 shadow-sm">
      <label className="text-xs font-medium text-slate-600">
        Da
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => onDateFrom(e.target.value)}
          className="mt-1 block rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-800"
        />
      </label>
      <label className="text-xs font-medium text-slate-600">
        A
        <input
          type="date"
          value={dateTo}
          onChange={(e) => onDateTo(e.target.value)}
          className="mt-1 block rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-800"
        />
      </label>
      <label className="text-xs font-medium text-slate-600">
        Competition ID
        <input
          value={competitionId}
          onChange={(e) => onCompetitionId(e.target.value)}
          placeholder="opzionale"
          className="mt-1 block w-28 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-800"
        />
      </label>
      <button
        type="button"
        disabled={loading}
        onClick={onRefresh}
        className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
      >
        Aggiorna
      </button>
    </div>
  )
}
