import { useCallback, useRef, useState } from 'react'
import {
  getPurchasabilityStatisticalResearch,
  type PurchasabilityStatFilters,
  type PurchasabilityStatisticalResearchResponse,
} from '../lib/cecchinoPurchasabilityStatisticalApi'

function defaultRange(): { date_from: string; date_to: string } {
  const to = new Date()
  const from = new Date()
  from.setDate(from.getDate() - 90)
  const fmt = (d: Date) => d.toISOString().slice(0, 10)
  return { date_from: fmt(from), date_to: fmt(to) }
}

export function useCecchinoPurchasabilityStatisticalResearch() {
  const defaults = defaultRange()
  const [dateFrom, setDateFrom] = useState(defaults.date_from)
  const [dateTo, setDateTo] = useState(defaults.date_to)
  const [selection, setSelection] = useState('')
  const [bootstrapIterations, setBootstrapIterations] = useState(200)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<PurchasabilityStatisticalResearchResponse | null>(null)
  const loadingRef = useRef(false)

  const filters = useCallback((): PurchasabilityStatFilters => {
    return {
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      selection: selection || undefined,
      bootstrap_iterations: bootstrapIterations,
      seed: 42,
    }
  }, [dateFrom, dateTo, selection, bootstrapIterations])

  const load = useCallback(async () => {
    if (loadingRef.current) return
    loadingRef.current = true
    setLoading(true)
    setError(null)
    try {
      const payload = await getPurchasabilityStatisticalResearch(filters())
      setData(payload)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }, [filters])

  return {
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    selection,
    setSelection,
    bootstrapIterations,
    setBootstrapIterations,
    loading,
    error,
    data,
    filters,
    load,
  }
}
