import { useId } from 'react'
import type { ModelRelevantArea, ModelRelevantField } from '../../lib/api'
import { ModelRelevantFieldRow } from './ModelRelevantFieldRow'

type Props = {
  area: ModelRelevantArea
  parameters: ModelRelevantField[]
  open: boolean
  onToggle: () => void
  showCheckbox: boolean
  selectedIds: Set<string>
  onToggleSelect?: (key: string) => void
}

export function ModelRelevantAreaSection({
  area,
  parameters,
  open,
  onToggle,
  showCheckbox,
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
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-slate-600">
          <span className="rounded-lg bg-slate-100 px-2 py-1 font-medium text-slate-800">Campi: {parameters.length}</span>
          <span className="rounded-lg bg-slate-50 px-2 py-1 font-medium text-slate-700">{open ? '▼' : '▶'}</span>
        </div>
      </button>
      {open ? (
        <div id={panelId} role="region" aria-labelledby={btnId} className="space-y-2 border-t border-slate-100 px-4 py-3 sm:px-5">
          {parameters.length === 0 ? (
            <p className="text-sm text-slate-500">Nessun campo in questa area con i filtri attuali.</p>
          ) : (
            parameters.map((p) => (
              <ModelRelevantFieldRow
                key={p.key}
                field={p}
                showCheckbox={showCheckbox}
                selected={selectedIds.has(p.key)}
                onToggle={onToggleSelect}
              />
            ))
          )}
        </div>
      ) : null}
    </section>
  )
}
