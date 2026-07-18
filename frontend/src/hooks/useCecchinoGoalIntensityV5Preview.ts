import { useCallback, useState } from 'react'
import {
  downloadGoalIntensityV5PreviewExport,
  fetchGoalIntensityV5Preview,
  fetchGoalIntensityV5PreviewMonitoring,
  refreshGoalIntensityV5Preview,
  type GoalIntensityV5PreviewExportKind,
  type GoalIntensityV5PreviewListResponse,
  type GoalIntensityV5PreviewMonitoringResponse,
  type GoalIntensityV5PreviewRefreshResponse,
} from '../lib/cecchinoGoalIntensityV5PreviewApi'
import { formatFetchError } from '../utils/formatFetchError'

type Filters = {
  dateFrom: string
  dateTo: string
  competitionId: string
  status: string
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function useCecchinoGoalIntensityV5Preview(filters: Filters) {
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [list, setList] = useState<GoalIntensityV5PreviewListResponse | null>(null)
  const [monitoring, setMonitoring] = useState<GoalIntensityV5PreviewMonitoringResponse | null>(
    null,
  )
  const [lastRefresh, setLastRefresh] = useState<GoalIntensityV5PreviewRefreshResponse | null>(
    null,
  )

  const load = useCallback(async (statusOverride?: string) => {
    setLoading(true)
    setError(null)
    try {
      const compId = filters.competitionId.trim() ? Number(filters.competitionId) : null
      const status = statusOverride !== undefined ? statusOverride : filters.status
      const [listRes, monRes] = await Promise.all([
        fetchGoalIntensityV5Preview({
          date_from: filters.dateFrom || undefined,
          date_to: filters.dateTo || undefined,
          competition_id:
            compId != null && Number.isFinite(compId) && compId > 0 ? compId : null,
          status: status || undefined,
          limit: 100,
          offset: 0,
        }),
        fetchGoalIntensityV5PreviewMonitoring(),
      ])
      setList(listRes)
      setMonitoring(monRes)
    } catch (err) {
      setError(formatFetchError(err))
      setList(null)
      setMonitoring(null)
    } finally {
      setLoading(false)
    }
  }, [filters.competitionId, filters.dateFrom, filters.dateTo, filters.status])

  const refresh = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      const compId = filters.competitionId.trim() ? Number(filters.competitionId) : null
      const report = await refreshGoalIntensityV5Preview({
        date_from: filters.dateFrom || null,
        date_to: filters.dateTo || null,
        competition_id:
          compId != null && Number.isFinite(compId) && compId > 0 ? compId : null,
      })
      setLastRefresh(report)
      await load()
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setRefreshing(false)
    }
  }, [filters.competitionId, filters.dateFrom, filters.dateTo, load])

  const exportKind = useCallback(async (kind: GoalIntensityV5PreviewExportKind) => {
    const { blob, filename } = await downloadGoalIntensityV5PreviewExport(kind)
    downloadBlob(blob, filename)
  }, [])

  return {
    loading,
    refreshing,
    error,
    list,
    monitoring,
    lastRefresh,
    load,
    refresh,
    exportKind,
  }
}
