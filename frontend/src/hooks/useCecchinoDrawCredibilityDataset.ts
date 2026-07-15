import { useCallback, useState } from 'react'
import {
  postDrawCredibilityDataset,
  postDrawCredibilityDatasetExportCsv,
  type DrawCredibilityCohort,
  type DrawCredibilityDatasetResponse,
} from '../lib/cecchinoDrawCredibilityResearchApi'
import { formatFetchError } from '../utils/formatFetchError'

type SharedFilters = {
  dateFrom: string
  dateTo: string
  competitionId: string
}

export function useCecchinoDrawCredibilityDataset(shared: SharedFilters) {
  const [cohort, setCohort] = useState<DrawCredibilityCohort>('eligible_primary')
  const [pageSize, setPageSize] = useState(100)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dataset, setDataset] = useState<DrawCredibilityDatasetResponse | null>(null)

  const parseCompetitionId = useCallback(() => {
    const compId = shared.competitionId.trim() ? Number(shared.competitionId) : null
    return compId != null && Number.isFinite(compId) && compId > 0 ? compId : null
  }, [shared.competitionId])

  const loadDataset = useCallback(
    async (nextPage?: number) => {
      setLoading(true)
      setError(null)
      try {
        const targetPage = nextPage ?? page
        const result = await postDrawCredibilityDataset({
          date_from: shared.dateFrom,
          date_to: shared.dateTo,
          competition_id: parseCompetitionId(),
          cohort,
          page: targetPage,
          page_size: pageSize,
        })
        setDataset(result)
        setPage(result.pagination.page)
      } catch (err) {
        setError(formatFetchError(err))
        setDataset(null)
      } finally {
        setLoading(false)
      }
    },
    [cohort, page, pageSize, parseCompetitionId, shared.dateFrom, shared.dateTo],
  )

  const exportCsv = useCallback(async () => {
    setExporting(true)
    setError(null)
    try {
      const { blob, filename } = await postDrawCredibilityDatasetExportCsv({
        date_from: shared.dateFrom,
        date_to: shared.dateTo,
        competition_id: parseCompetitionId(),
        cohort,
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(formatFetchError(err))
    } finally {
      setExporting(false)
    }
  }, [cohort, parseCompetitionId, shared.dateFrom, shared.dateTo])

  return {
    cohort,
    page,
    pageSize,
    loading,
    exporting,
    error,
    dataset,
    setCohort,
    setPage,
    setPageSize,
    loadDataset,
    exportCsv,
  }
}
