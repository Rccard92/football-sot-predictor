import { useCompetition } from '../contexts/CompetitionContext'

function competitionLabel(c: { name: string; season: number; country?: string | null }) {
  const country = c.country ? `${c.country} · ` : ''
  return `${country}${c.name} ${c.season}`
}

export function CompetitionSelector({ collapsed = false }: { collapsed?: boolean }) {
  const { competitions, selectedCompetitionId, setSelectedCompetitionId, loading } = useCompetition()

  if (loading && competitions.length === 0) {
    return (
      <p className={`text-xs text-slate-500 ${collapsed ? 'text-center' : ''}`}>Caricamento…</p>
    )
  }

  if (collapsed) {
    return (
      <p
        className="truncate text-[10px] font-semibold text-slate-700"
        title={selectedCompetitionId ? 'Campionato attivo' : 'Nessun campionato'}
      >
        {competitions.find((c) => c.id === selectedCompetitionId)?.name?.slice(0, 3) ?? '—'}
      </p>
    )
  }

  return (
    <div className="space-y-1">
      <label htmlFor="competition-select" className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Campionato attivo
      </label>
      <select
        id="competition-select"
        className="w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-900 shadow-sm"
        value={selectedCompetitionId ?? ''}
        onChange={(e) => setSelectedCompetitionId(Number(e.target.value))}
      >
        {competitions.map((c) => (
          <option key={c.id} value={c.id}>
            {competitionLabel(c)}
          </option>
        ))}
      </select>
    </div>
  )
}

export function CompetitionBadge() {
  const { selectedCompetition } = useCompetition()
  if (!selectedCompetition) return null
  return (
    <span className="inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-800">
      {selectedCompetition.name} {selectedCompetition.season}
    </span>
  )
}
