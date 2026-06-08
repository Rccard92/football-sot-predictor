import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { SignalsActivationsTable } from '../components/cecchino/signals/SignalsActivationsTable'
import { SignalsHeatmapMatrix } from '../components/cecchino/signals/SignalsHeatmapMatrix'
import { SignalsMonitoringKpiCards } from '../components/cecchino/signals/SignalsMonitoringKpiCards'
import { SignalsTopRanking } from '../components/cecchino/signals/SignalsTopRanking'
import {
  backfillCecchinoSignals,
  buildCecchinoSignalsExportUrl,
  EVAL_STATUSES,
  getCecchinoSignalsActivations,
  getCecchinoSignalsSummary,
  revaluateCecchinoSignals,
  SIGNAL_GROUPS,
  SOURCE_COLUMNS,
  type SignalsDiagnostics,
  type SignalsFilters,
  type SignalsSummaryResponse,
  type SignalActivationRow,
} from '../lib/cecchinoSignalsApi'
import { updateCecchinoTodayResults } from '../lib/cecchinoTodayApi'
import { formatFetchError } from '../utils/formatFetchError'

function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export function CecchinoSignalsMonitoringPage() {
  const [searchParams] = useSearchParams()
  const [dateFrom, setDateFrom] = useState(searchParams.get('date_from') ?? isoDaysAgo(6))
  const [dateTo, setDateTo] = useState(searchParams.get('date_to') ?? todayIso())
  const [signalGroup, setSignalGroup] = useState(searchParams.get('signal_group') ?? '')
  const [sourceColumn, setSourceColumn] = useState(searchParams.get('source_column') ?? '')
  const [evaluationStatus, setEvaluationStatus] = useState('')
  const [countryName, setCountryName] = useState('')
  const [leagueName, setLeagueName] = useState('')
  const [summary, setSummary] = useState<SignalsSummaryResponse | null>(null)
  const [items, setItems] = useState<SignalActivationRow[]>([])
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  const filters: SignalsFilters = useMemo(
    () => ({
      date_from: dateFrom,
      date_to: dateTo,
      signal_group: signalGroup || undefined,
      source_column: sourceColumn || undefined,
      evaluation_status: evaluationStatus || undefined,
      country_name: countryName || undefined,
      league_name: leagueName || undefined,
      only_current: true,
      include_diagnostics: true,
    }),
    [dateFrom, dateTo, signalGroup, sourceColumn, evaluationStatus, countryName, leagueName],
  )

  const diagnostics: SignalsDiagnostics | undefined = summary?.diagnostics

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [summaryRes, listRes] = await Promise.all([
        getCecchinoSignalsSummary(filters),
        getCecchinoSignalsActivations({ ...filters, limit: 200, offset: 0 }),
      ])
      setSummary(summaryRes)
      setItems(listRes.items)
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    void loadData()
  }, [loadData])

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

  const handleRevaluate = async () => {
    setActionLoading(true)
    setActionMessage(null)
    try {
      const res = await revaluateCecchinoSignals({
        date_from: dateFrom,
        date_to: dateTo,
        sync_missing: true,
      })
      setActionMessage(
        `Rivalutazione completata: ${res.evaluated} valutati, ${res.pending} pending.`,
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

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Monitoraggio Segnali Cecchino</h1>
        <p className="mt-1 text-sm text-slate-600">
          Analisi aggregata dei segnali SI/NO e verifica dell&apos;esito reale dopo il risultato
          delle partite.
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
            onClick={() => void handleRevaluate()}
            disabled={actionLoading}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
          >
            Rivaluta segnali
          </button>
          <button
            type="button"
            onClick={handleExport}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
          >
            Esporta CSV
          </button>
        </div>
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

      {loading && !summary ? (
        <p className="text-sm text-slate-500">Caricamento...</p>
      ) : summary ? (
        <>
          <SignalsMonitoringKpiCards overall={summary.overall} />
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">Heatmap Segnale × Colonna</h2>
            <div className="mt-3">
              <SignalsHeatmapMatrix summary={summary} />
            </div>
            <p className="mt-3 text-xs text-slate-500">
              UNDER 2.5 e OVER 2.5 sono valutati sul risultato Full Time.
            </p>
          </section>
          <SignalsTopRanking summary={summary} />
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">Dettaglio partite</h2>
            <div className="mt-3">
              <SignalsActivationsTable items={items} />
            </div>
          </section>
        </>
      ) : null}
    </div>
  )
}
