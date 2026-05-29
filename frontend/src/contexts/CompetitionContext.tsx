import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  getCompetitions,
  getDefaultCompetition,
  type CompetitionSummary,
} from '../lib/api'

const STORAGE_KEY = 'sot_selected_competition_id'

type CompetitionContextValue = {
  competitions: CompetitionSummary[]
  selectedCompetition: CompetitionSummary | null
  selectedCompetitionId: number | null
  loading: boolean
  error: string | null
  setSelectedCompetitionId: (id: number) => void
  refreshCompetitions: () => Promise<void>
}

const CompetitionContext = createContext<CompetitionContextValue | null>(null)

export function CompetitionProvider({ children }: { children: ReactNode }) {
  const [competitions, setCompetitions] = useState<CompetitionSummary[]>([])
  const [selectedCompetitionId, setSelectedCompetitionIdState] = useState<number | null>(() => {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refreshCompetitions = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [list, def] = await Promise.all([getCompetitions(), getDefaultCompetition()])
      setCompetitions(list)
      setSelectedCompetitionIdState((prev) => {
        if (prev != null && list.some((c) => c.id === prev)) return prev
        const fallback = def?.id ?? list[0]?.id ?? null
        if (fallback != null) localStorage.setItem(STORAGE_KEY, String(fallback))
        return fallback
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshCompetitions()
  }, [refreshCompetitions])

  const setSelectedCompetitionId = useCallback((id: number) => {
    setSelectedCompetitionIdState(id)
    localStorage.setItem(STORAGE_KEY, String(id))
  }, [])

  const selectedCompetition = useMemo(
    () => competitions.find((c) => c.id === selectedCompetitionId) ?? null,
    [competitions, selectedCompetitionId],
  )

  const value = useMemo(
    () => ({
      competitions,
      selectedCompetition,
      selectedCompetitionId,
      loading,
      error,
      setSelectedCompetitionId,
      refreshCompetitions,
    }),
    [
      competitions,
      selectedCompetition,
      selectedCompetitionId,
      loading,
      error,
      setSelectedCompetitionId,
      refreshCompetitions,
    ],
  )

  return <CompetitionContext.Provider value={value}>{children}</CompetitionContext.Provider>
}

export function useCompetition() {
  const ctx = useContext(CompetitionContext)
  if (!ctx) {
    throw new Error('useCompetition must be used within CompetitionProvider')
  }
  return ctx
}
