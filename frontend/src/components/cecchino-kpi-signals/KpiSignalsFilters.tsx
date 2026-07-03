import { KPI_EVAL_STATUSES, KPI_RATING_BUCKETS } from '../../lib/cecchinoKpiSignalsApi'

type Props = {
  dateFrom: string
  dateTo: string
  ratingBucket: string
  selectionKey: string
  evaluationStatus: string
  countryName: string
  leagueName: string
  loading: boolean
  actionLoading: boolean
  onDateFromChange: (v: string) => void
  onDateToChange: (v: string) => void
  onRatingBucketChange: (v: string) => void
  onSelectionKeyChange: (v: string) => void
  onEvaluationStatusChange: (v: string) => void
  onCountryNameChange: (v: string) => void
  onLeagueNameChange: (v: string) => void
  onRefresh: () => void
  onSync: () => void
  onRevaluate: () => void
  onExport: () => void
}

export function KpiSignalsFilters({
  dateFrom,
  dateTo,
  ratingBucket,
  selectionKey,
  evaluationStatus,
  countryName,
  leagueName,
  loading,
  actionLoading,
  onDateFromChange,
  onDateToChange,
  onRatingBucketChange,
  onSelectionKeyChange,
  onEvaluationStatusChange,
  onCountryNameChange,
  onLeagueNameChange,
  onRefresh,
  onSync,
  onRevaluate,
  onExport,
}: Props) {
  const busy = loading || actionLoading
  return (
    <section className="sticky top-0 z-20 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm backdrop-blur">
      <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
        <label className="text-xs text-slate-600">
          Da
          <input type="date" className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={dateFrom} onChange={(e) => onDateFromChange(e.target.value)} />
        </label>
        <label className="text-xs text-slate-600">
          A
          <input type="date" className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={dateTo} onChange={(e) => onDateToChange(e.target.value)} />
        </label>
        <label className="text-xs text-slate-600">
          Bucket rating
          <select className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={ratingBucket} onChange={(e) => onRatingBucketChange(e.target.value)}>
            <option value="">Tutti</option>
            {KPI_RATING_BUCKETS.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-600">
          Pronostico (key)
          <input className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={selectionKey} onChange={(e) => onSelectionKeyChange(e.target.value)} placeholder="es. AWAY" />
        </label>
        <label className="text-xs text-slate-600">
          Stato
          <select className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={evaluationStatus} onChange={(e) => onEvaluationStatusChange(e.target.value)}>
            <option value="">Tutti</option>
            {KPI_EVAL_STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-600">
          Nazione
          <input className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={countryName} onChange={(e) => onCountryNameChange(e.target.value)} />
        </label>
        <label className="text-xs text-slate-600 lg:col-span-2">
          Campionato
          <input className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={leagueName} onChange={(e) => onLeagueNameChange(e.target.value)} />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50" disabled={busy} onClick={onRefresh}>Aggiorna</button>
        <button type="button" className="rounded-lg bg-cyan-700 px-3 py-1.5 text-sm text-white disabled:opacity-50" disabled={busy} onClick={onSync}>Sincronizza KPI</button>
        <button type="button" className="rounded-lg border px-3 py-1.5 text-sm disabled:opacity-50" disabled={busy} onClick={onRevaluate}>Rivaluta KPI</button>
        <button type="button" className="rounded-lg border px-3 py-1.5 text-sm disabled:opacity-50" disabled={busy} onClick={onExport}>Esporta CSV</button>
      </div>
    </section>
  )
}
