import { useCompetition } from '../contexts/CompetitionContext'

function competitionLabel(c: { name: string; season: number; country?: string | null }) {
  return `${c.name} · ${c.country ?? '?'} · ${c.season}`
}

export function CompetitionSelector({ collapsed = false }: { collapsed?: boolean }) {
  const {
    competitions,
    selectedCompetitionId,
    setSelectedCompetitionId,
    loading,
    emptyMessage,
    isConfigured,
  } = useCompetition()

  const hint =
    emptyMessage ?? 'Nessun campionato configurato. Vai in Admin e fai Backfill Serie A.'

  if (loading && competitions.length === 0) {
    return (
      <p className={`text-xs text-slate-500 ${collapsed ? 'text-center' : ''}`}>Caricamento…</p>
    )
  }

  if (collapsed) {
    return (
      <p
        className="truncate text-[10px] font-semibold text-slate-700"
        title={selectedCompetitionId ? 'Campionato attivo' : hint}
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
        className="w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-900 shadow-sm disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500"
        value={selectedCompetitionId ?? ''}
        disabled={!isConfigured}
        onChange={(e) => setSelectedCompetitionId(Number(e.target.value))}
      >
        {!isConfigured ? <option value="">Nessun campionato</option> : null}
        {competitions.map((c) => (
          <option key={c.id} value={c.id}>
            {competitionLabel(c)}
          </option>
        ))}
      </select>
      {!isConfigured ? <p className="text-[11px] leading-snug text-amber-700">{hint}</p> : null}
    </div>
  )
}

export function CompetitionBadge() {
  const { selectedCompetition } = useCompetition()
  if (!selectedCompetition) return null
  return (
    <span className="inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-800">
      {competitionLabel(selectedCompetition)}
    </span>
  )
}
