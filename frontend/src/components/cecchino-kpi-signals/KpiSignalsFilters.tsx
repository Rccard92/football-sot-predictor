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

function Spinner() {
  return (
    <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
  )
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
  const inputClass =
    'mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm shadow-sm transition-shadow focus:border-cyan-300 focus:outline-none focus:ring-2 focus:ring-cyan-100'
  const busy = loading || actionLoading

  return (
    <section className="sticky top-0 z-20 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm backdrop-blur-sm">
      <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
        <label className="text-xs font-medium text-slate-600">
          Da
          <input type="date" className={inputClass} value={dateFrom} onChange={(e) => onDateFromChange(e.target.value)} />
        </label>
        <label className="text-xs font-medium text-slate-600">
          A
          <input type="date" className={inputClass} value={dateTo} onChange={(e) => onDateToChange(e.target.value)} />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Bucket rating
          <select className={inputClass} value={ratingBucket} onChange={(e) => onRatingBucketChange(e.target.value)}>
            <option value="">Tutti</option>
            {KPI_RATING_BUCKETS.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Pronostico (key)
          <input
            className={inputClass}
            value={selectionKey}
            onChange={(e) => onSelectionKeyChange(e.target.value)}
            placeholder="es. AWAY"
          />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Stato
          <select
            className={inputClass}
            value={evaluationStatus}
            onChange={(e) => onEvaluationStatusChange(e.target.value)}
          >
            <option value="">Tutti</option>
            {KPI_EVAL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Nazione
          <input
            className={inputClass}
            value={countryName}
            onChange={(e) => onCountryNameChange(e.target.value)}
            placeholder="opzionale"
          />
        </label>
        <label className="text-xs font-medium text-slate-600 lg:col-span-2">
          Campionato
          <input
            className={inputClass}
            value={leagueName}
            onChange={(e) => onLeagueNameChange(e.target.value)}
            placeholder="opzionale"
          />
        </label>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={onRefresh}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
        >
          {loading ? <Spinner /> : null}
          Aggiorna
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onSync}
          className="inline-flex items-center gap-2 rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm font-medium text-cyan-900 transition hover:bg-cyan-100 disabled:opacity-50"
        >
          {actionLoading ? <Spinner /> : null}
          Sincronizza KPI
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onRevaluate}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
        >
          Rivaluta KPI
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onExport}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
        >
          Esporta CSV
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        La sincronizzazione KPI usa solo dati già presenti nel DB e non consuma API.
      </p>
    </section>
  )
}
