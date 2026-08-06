import {
  ACQUISITION_FILTER_OPTIONS,
  EVAL_STATUSES,
  SIGNAL_FORMULA_CURRENT_BADGE,
  SIGNAL_GROUPS,
  SOURCE_COLUMNS,
} from '../../lib/cecchinoSignalsApi'

type Props = {
  dateFrom: string
  dateTo: string
  signalGroup: string
  sourceColumn: string
  evaluationStatus: string
  countryName: string
  leagueName: string
  signalFormulaVersion: string
  acquisitionFilter: string
  consensusYesCountMin: number | undefined
  loading: boolean
  actionLoading: boolean
  onDateFromChange: (v: string) => void
  onDateToChange: (v: string) => void
  onSignalGroupChange: (v: string) => void
  onSourceColumnChange: (v: string) => void
  onEvaluationStatusChange: (v: string) => void
  onCountryNameChange: (v: string) => void
  onLeagueNameChange: (v: string) => void
  onSignalFormulaVersionChange: (v: string) => void
  onAcquisitionFilterChange: (v: string) => void
  onConsensusYesCountMinChange: (v: number | undefined) => void
  onRefresh: () => void
  onBacktest: () => void
  onRevaluate: () => void
  onExport: () => void
}

function Spinner() {
  return (
    <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
  )
}

export function SignalsLabFilters({
  dateFrom,
  dateTo,
  signalGroup,
  sourceColumn,
  evaluationStatus,
  countryName,
  leagueName,
  acquisitionFilter,
  consensusYesCountMin,
  loading,
  actionLoading,
  onDateFromChange,
  onDateToChange,
  onSignalGroupChange,
  onSourceColumnChange,
  onEvaluationStatusChange,
  onCountryNameChange,
  onLeagueNameChange,
  onAcquisitionFilterChange,
  onConsensusYesCountMinChange,
  onRefresh,
  onBacktest,
  onRevaluate,
  onExport,
}: Props) {
  const inputClass =
    'mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm shadow-sm transition-shadow focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100'

  return (
    <section className="sticky top-0 z-20 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm backdrop-blur-sm">
      <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
        <label className="text-xs font-medium text-slate-600">
          Da
          <input type="date" value={dateFrom} onChange={(e) => onDateFromChange(e.target.value)} className={inputClass} />
        </label>
        <label className="text-xs font-medium text-slate-600">
          A
          <input type="date" value={dateTo} onChange={(e) => onDateToChange(e.target.value)} className={inputClass} />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Segnale
          <select value={signalGroup} onChange={(e) => onSignalGroupChange(e.target.value)} className={inputClass}>
            {SIGNAL_GROUPS.map((opt) => (
              <option key={opt.value || 'all'} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Colonna
          <select value={sourceColumn} onChange={(e) => onSourceColumnChange(e.target.value)} className={inputClass}>
            {SOURCE_COLUMNS.map((opt) => (
              <option key={opt.value || 'all'} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Stato
          <select
            value={evaluationStatus}
            onChange={(e) => onEvaluationStatusChange(e.target.value)}
            className={inputClass}
          >
            {EVAL_STATUSES.map((opt) => (
              <option key={opt.value || 'all'} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Nazione
          <input
            type="text"
            value={countryName}
            onChange={(e) => onCountryNameChange(e.target.value)}
            placeholder="opzionale"
            className={inputClass}
          />
        </label>
        <label className="text-xs font-medium text-slate-600 lg:col-span-2">
          Campionato
          <input
            type="text"
            value={leagueName}
            onChange={(e) => onLeagueNameChange(e.target.value)}
            placeholder="opzionale"
            className={inputClass}
          />
        </label>
      </div>

      <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50/70 p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          Filtro Segnali Cecchino
        </p>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <div className="text-xs font-medium text-slate-600">
            Formula
            <div
              aria-label="Formula"
              className={`${inputClass} flex items-center bg-slate-100 font-semibold text-slate-800`}
            >
              <span className="inline-flex items-center rounded-md bg-indigo-50 px-2 py-0.5 text-indigo-800 ring-1 ring-inset ring-indigo-200">
                {SIGNAL_FORMULA_CURRENT_BADGE}
              </span>
            </div>
          </div>
          <label className="text-xs font-medium text-slate-600">
            Acquisizione
            <select
              aria-label="Acquisizione"
              value={acquisitionFilter}
              onChange={(e) => onAcquisitionFilterChange(e.target.value)}
              className={inputClass}
            >
              {ACQUISITION_FILTER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Conferme minime
            <input
              aria-label="Conferme minime"
              type="number"
              min={0}
              step={1}
              value={consensusYesCountMin ?? ''}
              onChange={(e) => {
                const raw = e.target.value.trim()
                if (!raw) {
                  onConsensusYesCountMinChange(undefined)
                  return
                }
                const parsed = Number(raw)
                onConsensusYesCountMinChange(Number.isFinite(parsed) ? parsed : undefined)
              }}
              placeholder="opzionale"
              className={inputClass}
            />
          </label>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading || actionLoading}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
        >
          {loading ? <Spinner /> : null}
          Aggiorna
        </button>
        <button
          type="button"
          onClick={onBacktest}
          disabled={actionLoading}
          className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-900 transition hover:bg-indigo-100 disabled:opacity-50"
        >
          {actionLoading ? <Spinner /> : null}
          Ricalcola modelli A–F su segnali a valore
        </button>
        <button
          type="button"
          onClick={onRevaluate}
          disabled={actionLoading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
        >
          Rivaluta segnali
        </button>
        <button
          type="button"
          onClick={onExport}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
        >
          Esporta CSV
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Il backtest modelli usa solo segnali a valore (quota book ≥ quota Cecchino e soglia minima)
        già presenti nel DB e non consuma API. Default: formula corrente e segni acquisiti.
      </p>
    </section>
  )
}
