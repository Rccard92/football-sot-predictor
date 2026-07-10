import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getSignalMinBookOddsSettings,
  resetSignalMinBookOddsDefaults,
  saveSignalMinBookOddsAndBacktest,
  updateSignalMinBookOddsSettings,
  formatMinBookOddsBacktestPanelMessage,
  type SignalMinBookOddSetting,
  type SignalMinBookOddsBacktestSummary,
} from '../../lib/cecchinoSignalsApi'
import { formatFetchError } from '../../utils/formatFetchError'
import { SIGNAL_VALUE_FILTER_NOTE } from './signalMinBookOdds'

type SignalMinBookOddsPanelProps = {
  variant?: 'monitoring' | 'lab'
  dateFrom: string
  dateTo: string
  onBacktestComplete?: (summary: SignalMinBookOddsBacktestSummary | null) => void | Promise<void>
}

type EditableRow = SignalMinBookOddSetting & { inputValue: string }

function daysBetween(from: string, to: string): number {
  const a = new Date(`${from}T00:00:00`)
  const b = new Date(`${to}T00:00:00`)
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) return 0
  return Math.round(Math.abs(b.getTime() - a.getTime()) / 86_400_000)
}

function validateOddInput(value: string): string | null {
  if (!value.trim()) return 'Valore obbligatorio'
  const num = Number(value.replace(',', '.'))
  if (!Number.isFinite(num)) return 'Numero non valido'
  if (num <= 1) return 'Deve essere > 1'
  if (num > 50) return 'Deve essere <= 50'
  const decimals = value.includes('.') ? value.split('.')[1]?.length ?? 0 : 0
  const decimalsComma = value.includes(',') ? value.split(',')[1]?.length ?? 0 : 0
  if (Math.max(decimals, decimalsComma) > 2) return 'Massimo 2 decimali'
  return null
}

function toPayloadItems(rows: EditableRow[]) {
  return rows.map((row) => ({
    target_market_key: row.target_market_key,
    min_book_odd: Number(row.inputValue.replace(',', '.')),
  }))
}

export function SignalMinBookOddsPanel({
  variant = 'monitoring',
  dateFrom,
  dateTo,
  onBacktestComplete,
}: SignalMinBookOddsPanelProps) {
  const isLab = variant === 'lab'
  const [rows, setRows] = useState<EditableRow[]>([])
  const [savedRows, setSavedRows] = useState<EditableRow[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [backtesting, setBacktesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [lastBacktest, setLastBacktest] = useState<SignalMinBookOddsBacktestSummary | null>(null)
  const [rebuildKpiFromCache, setRebuildKpiFromCache] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const loadSettings = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getSignalMinBookOddsSettings()
      const editable = res.items.map((item) => ({
        ...item,
        inputValue: item.min_book_odd.toFixed(2),
      }))
      setRows(editable)
      setSavedRows(editable)
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadSettings()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadSettings])

  const dirty = useMemo(
    () => rows.some((row, i) => row.inputValue !== savedRows[i]?.inputValue),
    [rows, savedRows],
  )

  const fieldErrors = useMemo(() => {
    const map: Record<string, string | null> = {}
    for (const row of rows) {
      map[row.target_market_key] = validateOddInput(row.inputValue)
    }
    return map
  }, [rows])

  const hasValidationErrors = Object.values(fieldErrors).some(Boolean)

  const handleInputChange = (key: string, value: string) => {
    setRows((prev) =>
      prev.map((row) =>
        row.target_market_key === key ? { ...row, inputValue: value } : row,
      ),
    )
    setSuccess(null)
  }

  const handleSave = async () => {
    if (hasValidationErrors) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const res = await updateSignalMinBookOddsSettings(toPayloadItems(rows))
      const editable = res.items.map((item) => ({
        ...item,
        inputValue: item.min_book_odd.toFixed(2),
      }))
      setRows(editable)
      setSavedRows(editable)
      setSuccess('Soglie salvate.')
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    if (!window.confirm('Ripristinare tutte le soglie ai valori default?')) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const res = await resetSignalMinBookOddsDefaults()
      const editable = res.items.map((item) => ({
        ...item,
        inputValue: item.min_book_odd.toFixed(2),
      }))
      setRows(editable)
      setSavedRows(editable)
      setSuccess('Soglie ripristinate ai default.')
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveAndBacktest = async () => {
    if (hasValidationErrors) return
    const spanDays = daysBetween(dateFrom, dateTo)
    if (spanDays > 7) {
      const ok = window.confirm(
        `Stai per ricalcolare un intervallo di ${spanDays + 1} giorni. Procedere?`,
      )
      if (!ok) return
    } else if (
      !window.confirm(
        'Salvare le soglie e ricalcolare il monitoraggio sul periodo selezionato?',
      )
    ) {
      return
    }

    setBacktesting(true)
    setError(null)
    setSuccess(null)
    try {
      const res = await saveSignalMinBookOddsAndBacktest({
        date_from: dateFrom,
        date_to: dateTo,
        items: toPayloadItems(rows),
        rebuild_kpi_from_cache: rebuildKpiFromCache,
        include_xpt: true,
        force_remap_signals: true,
        evaluate_after: true,
      })
      const editable = res.settings.map((item) => ({
        ...item,
        inputValue: item.min_book_odd.toFixed(2),
      }))
      setRows(editable)
      setSavedRows(editable)
      setLastBacktest(res.backtest)
      await onBacktestComplete?.(res.backtest)
      setSuccess(formatMinBookOddsBacktestPanelMessage(res.backtest, res.status))
      if (res.status === 'partial' && res.errors.length > 0) {
        setError(res.errors.slice(0, 3).join(' · '))
      }
    } catch (err) {
      setError(formatFetchError(err))
      onBacktestComplete?.(null)
    } finally {
      setBacktesting(false)
    }
  }

  const busy = saving || backtesting

  return (
    <section
      className={
        isLab
          ? 'rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50/40 via-white to-slate-50/60 p-5 shadow-sm'
          : 'rounded-lg border border-slate-200 bg-white p-4'
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">Soglie quota book</h2>
          <p className="mt-1 text-sm text-slate-600">{SIGNAL_VALUE_FILTER_NOTE}</p>
          <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Abbassare una soglia fa rientrare solo segnali che erano già SI nella matrice e già a
            valore rispetto alla quota Cecchino. Non trasforma formule NO in SI. Se quota book &lt;
            quota Cecchino o mancano quote, il segnale non entra comunque: la soglia minima è solo
            il terzo filtro.
          </p>
        </div>
        {dirty && (
          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800">
            Modifiche non salvate
          </span>
        )}
      </div>

      {loading ? (
        <p className="mt-4 text-sm text-slate-500">Caricamento soglie…</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-2 py-2">Segno</th>
                <th className="px-2 py-2">Soglia min</th>
                <th className="px-2 py-2">Default</th>
                <th className="px-2 py-2">Stato</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const err = fieldErrors[row.target_market_key]
                const modified =
                  row.inputValue !== row.default_min_book_odd.toFixed(2) ||
                  Number(row.inputValue.replace(',', '.')) !== row.default_min_book_odd
                return (
                  <tr key={row.target_market_key} className="border-b border-slate-100">
                    <td className="px-2 py-2 font-medium text-slate-800">{row.label}</td>
                    <td className="px-2 py-2">
                      <input
                        type="number"
                        step="0.01"
                        min={1.01}
                        max={50}
                        value={row.inputValue}
                        onChange={(e) => handleInputChange(row.target_market_key, e.target.value)}
                        className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm"
                        disabled={busy}
                      />
                      {err && <p className="mt-0.5 text-xs text-red-600">{err}</p>}
                    </td>
                    <td className="px-2 py-2 text-slate-600">
                      {row.default_min_book_odd.toFixed(2)}
                    </td>
                    <td className="px-2 py-2">
                      {modified ? (
                        <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs text-violet-800">
                          Modificato
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">Default</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={busy || loading || hasValidationErrors || !dirty}
          className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {saving ? 'Salvataggio…' : 'Salva'}
        </button>
        <button
          type="button"
          onClick={() => void handleSaveAndBacktest()}
          disabled={busy || loading || hasValidationErrors}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {backtesting ? 'Ricalcolo…' : 'Salva e ricalcola'}
        </button>
        <button
          type="button"
          onClick={() => void handleReset()}
          disabled={busy || loading}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 disabled:opacity-50"
        >
          Ripristina default
        </button>
      </div>

      <div className="mt-4">
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-xs font-medium text-indigo-700 hover:underline"
        >
          {showAdvanced ? 'Nascondi avanzate' : 'Mostra avanzate'}
        </button>
        {showAdvanced && (
          <label className="mt-2 flex items-start gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={rebuildKpiFromCache}
              onChange={(e) => setRebuildKpiFromCache(e.target.checked)}
              disabled={busy}
              className="mt-1"
            />
            <span>
              Ricostruisci KPI da cache prima del backtest. Usa questa opzione per provare a
              recuperare X PT sulle giornate storiche già scansionate. Non chiama API esterne.
            </span>
          </label>
        )}
      </div>

      {success && <p className="mt-3 text-sm text-emerald-700">{success}</p>}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {lastBacktest && (
        <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
          <p className="font-medium text-slate-800">Ultimo ricalcolo</p>
          <p className="mt-1">
            A valore (default): {lastBacktest.value_passed} · Sotto soglia:{' '}
            {lastBacktest.min_book_odd_skipped} · Disattivati soglia:{' '}
            {lastBacktest.deactivated_min_book_odd} · Celle SI: {lastBacktest.si_cells_seen}
            {lastBacktest.models_processed && lastBacktest.models_processed.length > 0
              ? ` · Modelli ricalcolati: ${lastBacktest.models_processed.join(', ')}`
              : ''}
            {lastBacktest.models_value_passed != null
              ? ` · A valore modelli A-F: ${lastBacktest.models_value_passed}`
              : ''}
          </p>
          <p className="mt-1">
            Quote mancanti book: {lastBacktest.missing_book_quote_skipped} · cecchino:{' '}
            {lastBacktest.missing_cecchino_quote_skipped}
          </p>
        </div>
      )}
    </section>
  )
}
