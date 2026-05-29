import { useCallback, useEffect, useState } from 'react'
import { Card } from '../components/ui/Card'
import { CompetitionBadge } from '../components/CompetitionSelector'
import { useCompetition } from '../contexts/CompetitionContext'
import { getCompetitionDataHealth } from '../lib/api'

export function DataHealth() {
  const { selectedCompetition, selectedCompetitionId } = useCompetition()
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoading(true)
    setError(null)
    try {
      setData(await getCompetitionDataHealth(selectedCompetitionId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selectedCompetitionId])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">
          Data Health{selectedCompetition ? ` — ${selectedCompetition.name}` : ''}
        </h1>
        <CompetitionBadge />
        <p className="mt-1 text-sm text-slate-600">
          Stato del database e delle pipeline per il campionato selezionato.
        </p>
      </header>
      <Card title="Metriche campionato">
        {loading ? <p className="text-sm text-slate-600">Caricamento…</p> : null}
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        {data ? (
          <pre className="max-h-[480px] overflow-auto rounded bg-slate-50 p-3 text-xs">{JSON.stringify(data, null, 2)}</pre>
        ) : null}
      </Card>
    </div>
  )
}
