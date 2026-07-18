import { useCallback, useState } from 'react'
import {
  getPurchasabilityAudit,
  getPurchasabilityDataset,
  type PurchasabilityAuditFilters,
  type PurchasabilityAuditResponse,
  type PurchasabilityDatasetResponse,
} from '../lib/cecchinoPurchasabilityResearchApi'

function defaultRange(): { date_from: string; date_to: string } {
  const to = new Date()
  const from = new Date()
  from.setDate(from.getDate() - 30)
  const fmt = (d: Date) => d.toISOString().slice(0, 10)
  return { date_from: fmt(from), date_to: fmt(to) }
}

export function useCecchinoPurchasabilityAudit() {
  const defaults = defaultRange()
  const [dateFrom, setDateFrom] = useState(defaults.date_from)
  const [dateTo, setDateTo] = useState(defaults.date_to)
  const [marketFamily, setMarketFamily] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [audit, setAudit] = useState<PurchasabilityAuditResponse | null>(null)
  const [dataset, setDataset] = useState<PurchasabilityDatasetResponse | null>(null)
  const [datasetOffset, setDatasetOffset] = useState(0)

  const filters = useCallback((): PurchasabilityAuditFilters => {
    return {
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      market_family: marketFamily || undefined,
    }
  }, [dateFrom, dateTo, marketFamily])

  const loadAudit = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const f = filters()
      const [a, d] = await Promise.all([
        getPurchasabilityAudit(f),
        getPurchasabilityDataset({ ...f, status: 'core', limit: 50, offset: datasetOffset }),
      ])
      setAudit(a)
      setDataset(d)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [filters, datasetOffset])

  const loadDatasetPage = useCallback(
    async (offset: number) => {
      setDatasetOffset(offset)
      setLoading(true)
      setError(null)
      try {
        const d = await getPurchasabilityDataset({
          ...filters(),
          status: 'core',
          limit: 50,
          offset,
        })
        setDataset(d)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    },
    [filters],
  )

  return {
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    marketFamily,
    setMarketFamily,
    loading,
    error,
    audit,
    dataset,
    datasetOffset,
    loadAudit,
    loadDatasetPage,
    filters,
  }
}
