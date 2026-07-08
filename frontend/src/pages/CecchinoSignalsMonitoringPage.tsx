import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { SignalsActivationsTable } from '../components/cecchino/signals/SignalsActivationsTable'
import { SignalsFormulaLegendAccordion } from '../components/cecchino/signals/SignalsFormulaLegendAccordion'
import { SignalsHeatmapMatrix } from '../components/cecchino/signals/SignalsHeatmapMatrix'
import { SignalsMonitoringKpiCards } from '../components/cecchino/signals/SignalsMonitoringKpiCards'
import { SignalsTopRanking } from '../components/cecchino/signals/SignalsTopRanking'
import { SignalsTakenOddsLegend } from '../components/cecchino/signals/SignalsTakenOddsLegend'
import { SignalsWeightModelCards } from '../components/cecchino/signals/SignalsWeightModelCards'
import {
  backfillCecchinoSignals,
  backtestCecchinoWeightModels,
  buildCecchinoSignalsExportUrl,
  CECCHINO_WEIGHT_MODEL_KEYS,
  DEFAULT_WEIGHT_MODEL_KEY,
  EVAL_STATUSES,
  getCecchinoSignalsActivations,
  getCecchinoSignalsModelsSummary,
  getCecchinoSignalsSummary,
  revaluateCecchinoSignals,
  SELECTED_MODEL_STORAGE_KEY,
  SIGNAL_GROUPS,
  SOURCE_COLUMNS,
  type ModelsSummaryResponse,
  type SignalsDiagnostics,
  type SignalsFilters,
  type SignalsSummaryResponse,
  type SignalActivationRow,
  type WeightModelSummary,
} from '../lib/cecchinoSignalsApi'
import { recomputeCecchino, updateCecchinoTodayResults } from '../lib/cecchinoTodayApi'
import { formatFetchError } from '../utils/formatFetchError'
import { todayLocalIso } from '../utils/dateLocal'

function readStoredModelKey(): string {
  try {
    return localStorage.getItem(SELECTED_MODEL_STORAGE_KEY) || DEFAULT_WEIGHT_MODEL_KEY
  } catch {
    return DEFAULT_WEIGHT_MODEL_KEY
  }
}

function resolveDefaultModelKey(models: WeightModelSummary[]): string {
  const f = models.find((m) => m.model_key === DEFAULT_WEIGHT_MODEL_KEY)
  if (f && f.activations > 0) return DEFAULT_WEIGHT_MODEL_KEY
  const withData = models.find((m) => m.activations > 0)
  if (withData) return withData.model_key
  return 'A'
}

export function CecchinoSignalsMonitoringPage() {
  const [searchParams] = useSearchParams()
  const [dateFrom, setDateFrom] = useState(searchParams.get('date_from') ?? todayLocalIso())
  const [dateTo, setDateTo] = useState(searchParams.get('date_to') ?? todayLocalIso())
  const [signalGroup, setSignalGroup] = useState(searchParams.get('signal_group') ?? '')
  const [sourceColumn, setSourceColumn] = useState(searchParams.get('source_column') ?? '')
  const [evaluationStatus, setEvaluationStatus] = useState('')
  const [countryName, setCountryName] = useState('')
  const [leagueName, setLeagueName] = useState('')
  const [selectedModelKey, setSelectedModelKey] = useState(readStoredModelKey)
  const [modelsSummary, setModelsSummary] = useState<ModelsSummaryResponse | null>(null)
  const [summary, setSummary] = useState<SignalsSummaryResponse | null>(null)
  const [items, setItems] = useState<SignalActivationRow[]>([])
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const defaultModelResolved = useRef(false)

  const filters: SignalsFilters = useMemo(
    () => ({
      date_from: dateFrom,
      date_to: dateTo,
      model_key: selectedModelKey,
      signal_group: signalGroup || undefined,
      source_column: sourceColumn || undefined,
      evaluation_status: evaluationStatus || undefined,
      country_name: countryName || undefined,
      league_name: leagueName || undefined,
      only_current: true,
      include_diagnostics: true,
    }),
    [
      dateFrom,
      dateTo,
      selectedModelKey,
      signalGroup,
      sourceColumn,
      evaluationStatus,
      countryName,
      leagueName,
    ],
  )

  const selectedModel = modelsSummary?.models.find((m) => m.model_key === selectedModelKey)
  const diagnostics: SignalsDiagnostics | undefined = summary?.diagnostics
  const hasAnyModelData = (modelsSummary?.models ?? []).some((m) => m.activations > 0)
  const hasFixturesInRange = (diagnostics?.today_fixtures_count ?? 0) > 0

  const handleSelectModel = useCallback((modelKey: string) => {
    setSelectedModelKey(modelKey)
    try {
      localStorage.setItem(SELECTED_MODEL_STORAGE_KEY, modelKey)
    } catch {
      /* ignore storage errors */
    }
  }, [])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const modelsRes = await getCecchinoSignalsModelsSummary({
        date_from: dateFrom,
        date_to: dateTo,
      })
      setModelsSummary(modelsRes)

      let modelKey = selectedModelKey
      if (!defaultModelResolved.current) {
        const stored = readStoredModelKey()
        const storedHasData = modelsRes.models.some(
          (m) => m.model_key === stored && m.activations > 0,
        )
        modelKey = storedHasData ? stored : resolveDefaultModelKey(modelsRes.models)
        defaultModelResolved.current = true
        if (modelKey !== selectedModelKey) {
          setSelectedModelKey(modelKey)
        }
      }

      const activeFilters: SignalsFilters = { ...filters, model_key: modelKey }
      const [summaryRes, listRes] = await Promise.all([
        getCecchinoSignalsSummary(activeFilters),
        getCecchinoSignalsActivations({ ...activeFilters, limit: 200, offset: 0 }),
      ])
      setSummary(summaryRes)
      setItems(listRes.items)
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo, filters, selectedModelKey])

  useEffect(() => {
    void loadData()
  }, [loadData])

  useEffect(() => {
    defaultModelResolved.current = false
  }, [dateFrom, dateTo])

  const handleBacktestModels = async () => {
    setActionLoading(true)
    setActionMessage(null)
    try {
      const res = await backtestCecchinoWeightModels({
        date_from: dateFrom,
        date_to: dateTo,
        models: [...CECCHINO_WEIGHT_MODEL_KEYS],
        force: true,
        evaluate_after: true,
        refresh_bookmaker_odds: false,
      })
      const total = res.by_model.reduce((acc, m) => acc + m.signals_created, 0)
      setActionMessage(
        `Backtest modelli A–F completato: ${res.fixtures_found} partite, ${total} segnali elaborati.`,
      )
      await loadData()
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setActionLoading(false)
    }
  }

  const handleUpdateResults = async () => {
    setActionLoading(true)
    setActionMessage(null)
    try {
      const res = await updateCecchinoTodayResults({ date: dateTo })
      setActionMessage(
        `Risultati aggiornati: ${res.results_updated ?? 0} partite, ${res.signals_evaluated ?? 0} segnali rivalutati.`,
      )
      await loadData()
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setActionLoading(false)
    }
  }

  const handleSyncSignals = async () => {
    setActionLoading(true)
    setActionMessage(null)
    try {
      const res = await backfillCecchinoSignals({
        date_from: dateFrom,
        date_to: dateTo,
        only_missing: true,
        evaluate_after: true,
      })
      if (res.signals_created + res.signals_updated === 0) {
        if (res.fixtures_with_signals === 0) {
          setActionMessage(
            'Trovate partite, ma nessuna matrice segnali disponibile nel periodo selezionato.',
          )
        } else {
          setActionMessage('Nessun nuovo segnale da sincronizzare.')
        }
      } else {
        setActionMessage(
          `Segnali sincronizzati: ${res.signals_created} creati, ${res.signals_updated} aggiornati.`,
        )
      }
      await loadData()
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setActionLoading(false)
    }
  }

  const VALUE_FILTER_CONFIRM =
    'Ricalcola il filtro valore su tutte le partite del periodo: restano monitorati solo i segnali SI con quota book ≥ quota Cecchino. Le activation senza valore verranno disattivate (nessuna cancellazione). Continuare?'

  const handleRemapMapping = async () => {
    if (!window.confirm(VALUE_FILTER_CONFIRM)) return
    setActionLoading(true)
    setActionMessage(null)
    try {
      const res = await backfillCecchinoSignals({
        date_from: dateFrom,
        date_to: dateTo,
        only_missing: false,
        evaluate_after: true,
        force_remap: true,
      })
      const missingQuotes = res.missing_value_quote ?? 0
      setActionMessage(
        `Filtro valore ricalcolato: ${res.si_cells_seen ?? 0} celle SI, ${res.value_passed ?? 0} a valore, ${res.no_value_skipped ?? 0} esclusi (quote mancanti: ${missingQuotes}, disattivati no-value: ${res.deactivated_no_value ?? 0}), ${res.evaluated ?? 0} rivalutati.`,
      )
      await loadData()
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setActionLoading(false)
    }
  }

  const handleRevaluate = async () => {
    setActionLoading(true)
    setActionMessage(null)
    try {
      const res = await revaluateCecchinoSignals({
        date_from: dateFrom,
        date_to: dateTo,
        sync_missing: true,
        refresh_signal_odds: true,
      })
      const oddsMsg = res.odds_refresh_summary
        ? ` Quote aggiornate: ${res.odds_refresh_summary.odds_refreshed}.`
        : ''
      setActionMessage(
        `Rivalutazione completata: ${res.evaluated} valutati, ${res.pending} pending.${oddsMsg}`,
      )
      await loadData()
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setActionLoading(false)
    }
  }

  const handleExport = () => {
    window.open(buildCecchinoSignalsExportUrl(filters), '_blank')
  }

  const RECOMPUTE_WARNING =
    'Il ricalcolo usa i nuovi pesi Cecchino e aggiorna KPI, segnali e monitoraggio usando i dati già presenti. Non consuma API se refresh quote è disattivato.'

  const handleRecomputeCecchino = async () => {
    if (!window.confirm(RECOMPUTE_WARNING)) return
    setActionLoading(true)
    setActionMessage(null)
    try {
      const res = await recomputeCecchino({
        date_from: dateFrom,
        date_to: dateTo,
      })
      setActionMessage(
        `Ricalcolo Cecchino: ${res.fixtures_recomputed}/${res.fixtures_found} partite, ${res.signals_synced} segnali sincronizzati, ${res.signals_deactivated} disattivati, ${res.signals_evaluated} rivalutati.`,
      )
      await loadData()
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Monitoraggio Segnali Cecchino</h1>
        <p className="mt-1 text-sm text-slate-600">
          Analisi aggregata dei segnali SI/NO e verifica dell&apos;esito reale dopo il risultato
          delle partite.
        </p>
        <p className="mt-2 rounded-md border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs text-cyan-900">
          Monitoraggio = segnali comprabili: SI + quota book ≥ quota Cecchino. La matrice in dettaglio
          partita resta invariata.
        </p>
        <p className="mt-2 rounded-md border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-900">
          X PT usa quote reali dal Pannello KPI (mercato primo tempo). Viene creato solo quando la X
          finale è accesa, passa il filtro valore e anche X PT ha quota book ≥ quota Cecchino.
        </p>
      </header>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
          <label className="text-xs text-slate-600">
            Da
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs text-slate-600">
            A
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs text-slate-600">
            Segnale
            <select
              value={signalGroup}
              onChange={(e) => setSignalGroup(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            >
              {SIGNAL_GROUPS.map((opt) => (
                <option key={opt.value || 'all'} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-600">
            Colonna
            <select
              value={sourceColumn}
              onChange={(e) => setSourceColumn(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            >
              {SOURCE_COLUMNS.map((opt) => (
                <option key={opt.value || 'all'} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-600">
            Stato
            <select
              value={evaluationStatus}
              onChange={(e) => setEvaluationStatus(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            >
              {EVAL_STATUSES.map((opt) => (
                <option key={opt.value || 'all'} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-600">
            Nazione
            <input
              type="text"
              value={countryName}
              onChange={(e) => setCountryName(e.target.value)}
              placeholder="opzionale"
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs text-slate-600 lg:col-span-2">
            Campionato
            <input
              type="text"
              value={leagueName}
              onChange={(e) => setLeagueName(e.target.value)}
              placeholder="opzionale"
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void loadData()}
            disabled={loading || actionLoading}
            className="rounded-md bg-slate-800 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            Aggiorna
          </button>
          <button
            type="button"
            onClick={() => void handleSyncSignals()}
            disabled={actionLoading}
            className="rounded-md border border-sky-300 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-800 hover:bg-sky-100 disabled:opacity-50"
          >
            Sincronizza segnali
          </button>
          <button
            type="button"
            onClick={() => void handleUpdateResults()}
            disabled={actionLoading}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
          >
            Aggiorna risultati giornata
          </button>
          <button
            type="button"
            onClick={() => void handleRemapMapping()}
            disabled={actionLoading}
            className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900 hover:bg-amber-100 disabled:opacity-50"
          >
            Ricalcola filtro valore
          </button>
          <button
            type="button"
            onClick={() => void handleRevaluate()}
            disabled={actionLoading}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
          >
            Rivaluta segnali
          </button>
          <button
            type="button"
            onClick={() => void handleBacktestModels()}
            disabled={actionLoading}
            className="rounded-md border border-indigo-300 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-900 hover:bg-indigo-100 disabled:opacity-50"
          >
            Ricalcola modelli A–F
          </button>
          <button
            type="button"
            onClick={() => void handleRecomputeCecchino()}
            disabled={actionLoading}
            className="rounded-md border border-violet-300 bg-violet-50 px-3 py-2 text-sm font-medium text-violet-900 hover:bg-violet-100 disabled:opacity-50"
          >
            Ricalcola Cecchino con nuovi pesi
          </button>
          <button
            type="button"
            onClick={handleExport}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
          >
            Esporta CSV
          </button>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Il backtest modelli usa solo segnali a valore (quota book ≥ quota Cecchino) già presenti nel DB
          e non consuma API.
        </p>
      </section>

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}
      {actionMessage && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {actionMessage}
        </p>
      )}

      {diagnostics && diagnostics.today_fixtures_count === 0 && (
        <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          Nessuna partita Cecchino trovata nel periodo selezionato.
        </p>
      )}

      {diagnostics &&
        diagnostics.today_fixtures_count > 0 &&
        diagnostics.current_signal_activations_count === 0 && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
            <p>
              Ci sono {diagnostics.today_fixtures_count} partite Cecchino nel periodo selezionato,
              ma i segnali non sono ancora stati sincronizzati. Clicca &quot;Sincronizza
              segnali&quot; per creare lo storico.
            </p>
            <button
              type="button"
              onClick={() => void handleSyncSignals()}
              disabled={actionLoading}
              className="mt-2 rounded-md bg-amber-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
            >
              Sincronizza ora
            </button>
          </div>
        )}

      {diagnostics &&
        diagnostics.current_signal_activations_count > 0 &&
        diagnostics.evaluated_count === 0 && (
          <p className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
            Segnali presenti ma non ancora valutati. Aggiorna i risultati o clicca Rivaluta segnali.
          </p>
        )}

      {diagnostics && (diagnostics.legacy_wrong_scala_mapping_count ?? 0) > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
          <p>
            Esistono {diagnostics.legacy_wrong_scala_mapping_count} activation legacy errate in
            SCALA su righe 1/2. Eseguire Ricalcola filtro valore.
          </p>
          <button
            type="button"
            onClick={() => void handleRemapMapping()}
            disabled={actionLoading}
            className="mt-2 rounded-md bg-amber-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            Ricalcola filtro valore
          </button>
        </div>
      )}

      {hasFixturesInRange && !hasAnyModelData && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
          <p>
            Per questo intervallo non esiste ancora il backtest dei modelli. Clicca Ricalcola
            modelli A–F.
          </p>
          <button
            type="button"
            onClick={() => void handleBacktestModels()}
            disabled={actionLoading}
            className="mt-2 rounded-md bg-indigo-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Calcola modelli A–F
          </button>
        </div>
      )}

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-800">Confronto modelli pesi</h2>
        <p className="mt-1 text-xs text-slate-500">
          Backtest comparativo offline sui pesi 1X2 — non modifica il Cecchino Today live.
        </p>
        <div className="mt-3">
          <SignalsWeightModelCards
            models={modelsSummary?.models ?? []}
            selectedModelKey={selectedModelKey}
            loading={loading}
            onSelect={handleSelectModel}
          />
        </div>
      </section>

      {summary && (
        <SignalsMonitoringKpiCards
          overall={summary.overall}
          title={`Statistiche modello selezionato: ${selectedModel?.short_label ?? `Modello ${selectedModelKey}`}`}
        />
      )}
      {summary && <SignalsTakenOddsLegend />}

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-800">
          Heatmap Segnale × Colonna — {selectedModel?.short_label ?? `Modello ${selectedModelKey}`}
        </h2>
        {selectedModel && (
          <p className="mt-1 text-xs text-slate-500">
            Pesi: Totali {selectedModel.weights.split(' / ')[0]}%, Casa/Trasferta{' '}
            {selectedModel.weights.split(' / ')[1]}%, Ultime 6 {selectedModel.weights.split(' / ')[2]}%,
            Ultime 5 C/F {selectedModel.weights.split(' / ')[3]}%
          </p>
        )}
        <div className="mt-3">
          {summary ? (
            <SignalsHeatmapMatrix summary={summary} />
          ) : loading ? (
            <p className="text-sm text-slate-500">Caricamento heatmap...</p>
          ) : null}
        </div>
        <p className="mt-3 text-xs text-slate-500">
          UNDER 2.5 e OVER 2.5 sono valutati sul risultato Full Time.
        </p>
        <SignalsFormulaLegendAccordion />
      </section>

      {summary && (
        <>
          <SignalsTopRanking summary={summary} />
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">Dettaglio partite</h2>
            <div className="mt-3">
              <SignalsActivationsTable items={items} />
            </div>
          </section>
        </>
      )}
    </div>
  )
}
