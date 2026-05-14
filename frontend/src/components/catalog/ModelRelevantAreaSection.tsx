import { useId } from 'react'
import type { ModelRelevantField } from '../../lib/api'
import { isCatalogFieldSelected } from '../../utils/deduplicateCatalogFields'
import { ModelRelevantFieldRow } from './ModelRelevantFieldRow'

type Props = {
  title: string
  parameters: ModelRelevantField[]
  open: boolean
  onToggle: () => void
  /** Se definito, la checkbox è mostrata solo per i campi con key non in questo insieme (fonti tecniche). */
  technicalKeys?: Set<string>
  selectedIds: Set<string>
  onToggleSelect?: (field: ModelRelevantField) => void
  headerStats?: { total: number; usedV04: number; future: number }
  subsections?: { title: string; parameters: ModelRelevantField[] }[]
  sectionReviewPending?: boolean
}

export function ModelRelevantAreaSection({
  title,
  parameters,
  open,
  onToggle,
  technicalKeys,
  selectedIds,
  onToggleSelect,
  headerStats,
  subsections,
  sectionReviewPending,
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
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-slate-600">
          {sectionReviewPending ? (
            <span className="rounded-lg border border-amber-200 bg-amber-50 px-2 py-1 font-medium text-amber-950">
              Da revisionare
            </span>
          ) : null}
          <span className="rounded-lg bg-slate-100 px-2 py-1 font-medium text-slate-800">Campi: {parameters.length}</span>
          {headerStats ? (
            <>
              <span className="rounded-lg bg-violet-50 px-2 py-1 font-medium text-violet-900">v0.4: {headerStats.usedV04}</span>
              <span className="rounded-lg bg-amber-50 px-2 py-1 font-medium text-amber-950">Future: {headerStats.future}</span>
            </>
          ) : null}
          <span className="rounded-lg bg-slate-50 px-2 py-1 font-medium text-slate-700">{open ? '▼' : '▶'}</span>
        </div>
      </button>
      {open ? (
        <div id={panelId} role="region" aria-labelledby={btnId} className="space-y-2 border-t border-slate-100 px-4 py-3 sm:px-5">
          {parameters.length === 0 ? (
            <p className="text-sm text-slate-500">Nessun campo in questa area con i filtri attuali.</p>
          ) : subsections && subsections.length > 0 ? (
            <div className="space-y-5">
              {subsections.map((sub) => (
                <div key={sub.title} className="space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{sub.title}</h4>
                  <div className="space-y-2">
                    {sub.parameters.map((p) => (
                      <ModelRelevantFieldRow
                        key={p.key}
                        field={p}
                        showCheckbox={technicalKeys ? !technicalKeys.has(p.key) : true}
                        selected={isCatalogFieldSelected(p, selectedIds)}
                        onToggle={onToggleSelect}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            parameters.map((p) => (
              <ModelRelevantFieldRow
                key={p.key}
                field={p}
                showCheckbox={technicalKeys ? !technicalKeys.has(p.key) : true}
                selected={isCatalogFieldSelected(p, selectedIds)}
                onToggle={onToggleSelect}
              />
            ))
          )}
        </div>
      ) : null}
    </section>
  )
}
