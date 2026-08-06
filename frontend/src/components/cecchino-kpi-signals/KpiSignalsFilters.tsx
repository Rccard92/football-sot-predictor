import {
  KPI_EVAL_STATUSES,
  KPI_RATING_BUCKETS,
  KPI_SELECTION_OPTIONS,
} from '../../lib/cecchinoKpiSignalsApi'

type Props = {
  dateFrom: string
  dateTo: string
  ratingBucket: string
  selectionKey: string
  evaluationStatus: string
  countryName: string
  leagueName: string
  purchasabilityVersion: string
  purchasabilityStatus: string
  purchasabilityClass: string
  purchasabilityQuality: string
  purchasabilityScoreMin: number | ''
  purchasabilityScoreMax: number | ''
  purchasabilityScoreError: string | null
  loading: boolean
  actionLoading: boolean
  onDateFromChange: (v: string) => void
  onDateToChange: (v: string) => void
  onRatingBucketChange: (v: string) => void
  onSelectionKeyChange: (v: string) => void
  onEvaluationStatusChange: (v: string) => void
  onCountryNameChange: (v: string) => void
  onLeagueNameChange: (v: string) => void
  onPurchasabilityVersionChange: (v: string) => void
  onPurchasabilityStatusChange: (v: string) => void
  onPurchasabilityClassChange: (v: string) => void
  onPurchasabilityQualityChange: (v: string) => void
  onPurchasabilityScoreMinChange: (v: number | '') => void
  onPurchasabilityScoreMaxChange: (v: number | '') => void
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

function parseScoreInput(raw: string): number | '' {
  if (raw.trim() === '') return ''
  const n = Number(raw)
  if (Number.isNaN(n)) return ''
  return n
}

export function KpiSignalsFilters({
  dateFrom,
  dateTo,
  ratingBucket,
  selectionKey,
  evaluationStatus,
  countryName,
  leagueName,
  purchasabilityVersion,
  purchasabilityStatus,
  purchasabilityClass,
  purchasabilityQuality,
  purchasabilityScoreMin,
  purchasabilityScoreMax,
  purchasabilityScoreError,
  loading,
  actionLoading,
  onDateFromChange,
  onDateToChange,
  onRatingBucketChange,
  onSelectionKeyChange,
  onEvaluationStatusChange,
  onCountryNameChange,
  onLeagueNameChange,
  onPurchasabilityVersionChange,
  onPurchasabilityStatusChange,
  onPurchasabilityClassChange,
  onPurchasabilityQualityChange,
  onPurchasabilityScoreMinChange,
  onPurchasabilityScoreMaxChange,
  onRefresh,
  onSync,
  onRevaluate,
  onExport,
}: Props) {
  const inputClass =
    'mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm shadow-sm transition-shadow focus:border-cyan-300 focus:outline-none focus:ring-2 focus:ring-cyan-100'
  const busy = loading || actionLoading
  const purchDisabled = !purchasabilityVersion

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
          Pronostico
          <select className={inputClass} value={selectionKey} onChange={(e) => onSelectionKeyChange(e.target.value)}>
            <option value="">Tutti</option>
            {KPI_SELECTION_OPTIONS.map((opt) => (
              <option key={opt.key} value={opt.key}>
                {opt.label}
              </option>
            ))}
          </select>
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

      <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50/60 p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Acquistabilità</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3 lg:grid-cols-6">
          <label className="text-xs font-medium text-slate-600">
            Versione
            <select
              className={inputClass}
              value={purchasabilityVersion}
              onChange={(e) => onPurchasabilityVersionChange(e.target.value)}
            >
              <option value="">Nessun filtro</option>
              <option value="v3">V3 attuale</option>
              <option value="v31">V3.1</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Stato
            <select
              aria-label="Stato Acquistabilità"
              className={inputClass}
              value={purchasabilityStatus}
              disabled={purchDisabled}
              onChange={(e) => onPurchasabilityStatusChange(e.target.value)}
            >
              <option value="">Tutti</option>
              <option value="score">Score disponibile</option>
              <option value="score_provisional">Score provvisorio</option>
              <option value="gate_failed">Non attivato</option>
              <option value="non_calculable">Non calcolabile</option>
              <option value="unsupported_market">Non supportato</option>
              <option value="snapshot_unavailable">Snapshot non disponibile</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Classe
            <select
              className={inputClass}
              value={purchasabilityClass}
              disabled={purchDisabled}
              onChange={(e) => onPurchasabilityClassChange(e.target.value)}
            >
              <option value="">Tutte</option>
              <option value="very_low">Molto Bassa</option>
              <option value="low">Bassa</option>
              <option value="medium">Media</option>
              <option value="high">Alta</option>
              <option value="very_high">Molto Alta</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Qualità
            <select
              className={inputClass}
              value={purchasabilityQuality}
              disabled={purchDisabled}
              onChange={(e) => onPurchasabilityQualityChange(e.target.value)}
            >
              <option value="">Tutte</option>
              <option value="full">Completa</option>
              <option value="provisional">Provvisoria</option>
              <option value="not_applicable">Non applicabile</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Score minimo
            <input
              type="number"
              min={0}
              max={100}
              className={inputClass}
              value={purchasabilityScoreMin}
              disabled={purchDisabled}
              onChange={(e) => onPurchasabilityScoreMinChange(parseScoreInput(e.target.value))}
              placeholder="0–100"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Score massimo
            <input
              type="number"
              min={0}
              max={100}
              className={inputClass}
              value={purchasabilityScoreMax}
              disabled={purchDisabled}
              onChange={(e) => onPurchasabilityScoreMaxChange(parseScoreInput(e.target.value))}
              placeholder="0–100"
            />
          </label>
        </div>
        {purchasabilityScoreError ? (
          <p className="mt-2 text-xs text-rose-600">{purchasabilityScoreError}</p>
        ) : null}
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
        La sincronizzazione KPI usa solo dati già presenti nel DB e non consuma API. L&apos;Acquistabilità è
        solo filtro storico, non gate di attivazione.
      </p>
    </section>
  )
}
