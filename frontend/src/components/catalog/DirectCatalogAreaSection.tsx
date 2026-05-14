import { useId } from 'react'
import type { ApiFootballDirectArea, ApiFootballDirectField } from '../../lib/api'
import { DirectCatalogParameterCard } from './DirectCatalogParameterCard'

type Props = {
  area: ApiFootballDirectArea
  parameters: ApiFootballDirectField[]
  open: boolean
  onToggle: () => void
  selectedIds: Set<string>
  onToggleSelect: (stableId: string) => void
}

export function DirectCatalogAreaSection({
  area,
  parameters,
  open,
  onToggle,
  selectedIds,
  onToggleSelect,
}: Props) {
  const panelId = useId()
  const btnId = useId()

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
      <button
        type="button"
        id={btnId}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
        className="flex w-full flex-col gap-1 px-4 py-3 text-left transition-colors hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between sm:px-5 sm:py-4"
      >
        <div>
          <h3 className="text-base font-semibold text-slate-900">{area.title}</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Endpoint: {area.endpoints.length ? area.endpoints.join(', ') : '—'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-slate-600">
          <span className="rounded-lg bg-slate-100 px-2 py-1 font-medium text-slate-800">Campi: {area.direct_fields_found}</span>
          <span className="rounded-lg bg-emerald-50 px-2 py-1 font-medium text-emerald-900">In DB: {area.fields_saved_in_db}</span>
          <span className="rounded-lg bg-amber-50 px-2 py-1 font-medium text-amber-900">raw_json: {area.fields_raw_json_only}</span>
          <span className="rounded-lg bg-violet-50 px-2 py-1 font-medium text-violet-900">v0.4: {area.fields_used_by_v04}</span>
          <span className="rounded-lg bg-slate-50 px-2 py-1 font-medium text-slate-700">{open ? '▼' : '▶'}</span>
        </div>
      </button>
      {open ? (
        <div id={panelId} role="region" aria-labelledby={btnId} className="space-y-3 border-t border-slate-100 px-4 py-4 sm:px-5">
          {parameters.length === 0 ? (
            <p className="text-sm text-slate-500">Nessun campo in questa area con i filtri attuali.</p>
          ) : (
            parameters.map((p) => (
              <DirectCatalogParameterCard
                key={p.stable_id}
                field={p}
                selected={selectedIds.has(p.stable_id)}
                onToggle={onToggleSelect}
              />
            ))
          )}
        </div>
      ) : null}
    </section>
  )
}
