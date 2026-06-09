import { useCallback, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  DEFAULT_WEIGHT_MODEL_KEY,
  backtestCecchinoWeightModels,
  buildCecchinoSignalsExportUrl,
  CECCHINO_WEIGHT_MODEL_KEYS,
  getCecchinoSignalsActivations,
  getCecchinoSignalsModelsSummary,
  getCecchinoSignalsSummary,
  revaluateCecchinoSignals,
  type ModelsSummaryResponse,
  type SignalActivationRow,
  type SignalsFilters,
  type SignalsSummaryResponse,
  type WeightModelSummary,
} from '../lib/cecchinoSignalsApi'
import { formatFetchError } from '../utils/formatFetchError'
import {
  isoDaysAgo,
  LAB_SELECTED_MODEL_KEY,
  todayIso,
} from '../components/cecchino-lab/signalsLabUtils'

function readStoredModelKey(): string {
  try {
    return localStorage.getItem(LAB_SELECTED_MODEL_KEY) || DEFAULT_WEIGHT_MODEL_KEY
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

export function useCecchinoSignalsLab() {
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(6))
  const [dateTo, setDateTo] = useState(todayIso())
  const [signalGroup, setSignalGroup] = useState('')
  const [sourceColumn, setSourceColumn] = useState('')
  const [evaluationStatus, setEvaluationStatus] = useState('')
  const [countryName, setCountryName] = useState('')
  const [leagueName, setLeagueName] = useState('')
  const [selectedModelKey, setSelectedModelKey] = useState(readStoredModelKey)
  const [modelsSummary, setModelsSummary] = useState<ModelsSummaryResponse | null>(null)
  const [summary, setSummary] = useState<SignalsSummaryResponse | null>(null)
  const [activations, setActivations] = useState<SignalActivationRow[]>([])
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
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
  const hasAnyModelData = (modelsSummary?.models ?? []).some((m) => m.activations > 0)
  const hasFixturesInRange = (summary?.diagnostics?.today_fixtures_count ?? 0) > 0

  const loadFilteredData = useCallback(
    async (modelKey: string, activeFilters: SignalsFilters) => {
      const withModel = { ...activeFilters, model_key: modelKey }
      const [summaryRes, listRes] = await Promise.all([
        getCecchinoSignalsSummary(withModel),
        getCecchinoSignalsActivations({ ...withModel, limit: 200, offset: 0 }),
      ])
      setSummary(summaryRes)
      setActivations(listRes.items)
    },
    [],
  )

  const loadAll = useCallback(async () => {
    setLoading(true)
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

      await loadFilteredData(modelKey, { ...filters, model_key: modelKey })
    } catch (err) {
      toast.error('Errore durante il caricamento dati', {
        description: formatFetchError(err),
      })
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo, filters, loadFilteredData, selectedModelKey])

  const resetDefaultOnDateChange = useCallback(() => {
    defaultModelResolved.current = false
  }, [])

  const selectModel = useCallback(
    async (modelKey: string) => {
      setSelectedModelKey(modelKey)
      try {
        localStorage.setItem(LAB_SELECTED_MODEL_KEY, modelKey)
      } catch {
        /* ignore */
      }
      setLoading(true)
      try {
        await loadFilteredData(modelKey, { ...filters, model_key: modelKey })
      } catch (err) {
        toast.error('Errore durante il caricamento dati', {
          description: formatFetchError(err),
        })
      } finally {
        setLoading(false)
      }
    },
    [filters, loadFilteredData],
  )

  const runBacktest = useCallback(async () => {
    setActionLoading(true)
    try {
      await backtestCecchinoWeightModels({
        date_from: dateFrom,
        date_to: dateTo,
        models: [...CECCHINO_WEIGHT_MODEL_KEYS],
        force: true,
        evaluate_after: true,
        refresh_bookmaker_odds: false,
      })
      toast.success('Backtest modelli completato')
      await loadAll()
    } catch (err) {
      toast.error('Errore durante il backtest', { description: formatFetchError(err) })
    } finally {
      setActionLoading(false)
    }
  }, [dateFrom, dateTo, loadAll])

  const runRevaluate = useCallback(async () => {
    setActionLoading(true)
    try {
      await revaluateCecchinoSignals({
        date_from: dateFrom,
        date_to: dateTo,
        sync_missing: true,
        refresh_signal_odds: true,
      })
      toast.success('Segnali rivalutati')
      await loadAll()
    } catch (err) {
      toast.error('Errore durante la rivalutazione', { description: formatFetchError(err) })
    } finally {
      setActionLoading(false)
    }
  }, [dateFrom, dateTo, loadAll])

  const exportCsv = useCallback(() => {
    window.open(buildCecchinoSignalsExportUrl(filters), '_blank')
  }, [filters])

  return {
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    signalGroup,
    setSignalGroup,
    sourceColumn,
    setSourceColumn,
    evaluationStatus,
    setEvaluationStatus,
    countryName,
    setCountryName,
    leagueName,
    setLeagueName,
    selectedModelKey,
    selectedModel,
    modelsSummary,
    summary,
    activations,
    loading,
    actionLoading,
    filters,
    hasAnyModelData,
    hasFixturesInRange,
    loadAll,
    selectModel,
    runBacktest,
    runRevaluate,
    exportCsv,
    resetDefaultOnDateChange,
  }
}
