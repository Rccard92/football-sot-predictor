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

const EMPTY_MESSAGE_DEFAULT =
  'Nessun campionato configurato. Vai in Admin e fai Backfill Serie A.'

type CompetitionContextValue = {
  competitions: CompetitionSummary[]
  selectedCompetition: CompetitionSummary | null
  selectedCompetitionId: number | null
  loading: boolean
  error: string | null
  emptyMessage: string | null
  isConfigured: boolean
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
  const [emptyMessage, setEmptyMessage] = useState<string | null>(null)

  const refreshCompetitions = useCallback(async () => {
    setLoading(true)
    setError(null)
    setEmptyMessage(null)
    try {
      const list = await getCompetitions()
      setCompetitions(list)

      if (list.length === 0) {
        const defRes = await getDefaultCompetition()
        setEmptyMessage(defRes.message ?? EMPTY_MESSAGE_DEFAULT)
        setSelectedCompetitionIdState(null)
        localStorage.removeItem(STORAGE_KEY)
        return
      }

      const storedRaw = localStorage.getItem(STORAGE_KEY)
      const storedId = storedRaw ? Number(storedRaw) : null
      const storedValid =
        storedId != null && Number.isFinite(storedId) && list.some((c) => c.id === storedId)

      if (storedValid) {
        setSelectedCompetitionIdState(storedId)
        return
      }

      const defRes = await getDefaultCompetition()
      const fallback = defRes.competition?.id ?? list[0]?.id ?? null
      if (fallback != null) {
        setSelectedCompetitionIdState(fallback)
        localStorage.setItem(STORAGE_KEY, String(fallback))
      } else {
        setSelectedCompetitionIdState(null)
        setEmptyMessage(defRes.message ?? EMPTY_MESSAGE_DEFAULT)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setCompetitions([])
      setEmptyMessage(EMPTY_MESSAGE_DEFAULT)
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
    setEmptyMessage(null)
  }, [])

  const selectedCompetition = useMemo(
    () => competitions.find((c) => c.id === selectedCompetitionId) ?? null,
    [competitions, selectedCompetitionId],
  )

  const isConfigured = competitions.length > 0

  const value = useMemo(
    () => ({
      competitions,
      selectedCompetition,
      selectedCompetitionId,
      loading,
      error,
      emptyMessage,
      isConfigured,
      setSelectedCompetitionId,
      refreshCompetitions,
    }),
    [
      competitions,
      selectedCompetition,
      selectedCompetitionId,
      loading,
      error,
      emptyMessage,
      isConfigured,
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
