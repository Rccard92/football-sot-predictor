import { useId } from 'react'
import type { ApiFootballCatalogArea, ApiFootballCatalogParameter } from '../../lib/api'
import { CatalogParameterCard } from './CatalogParameterCard'

export type AreaHeaderStats = {
  total: number
  v04UsedOrIndirect: number
  implementedLike: number
  toImplementLike: number
}

type CatalogAreaSectionProps = {
  area: ApiFootballCatalogArea
  stats: AreaHeaderStats
  parameters: ApiFootballCatalogParameter[]
  open: boolean
  onToggle: () => void
  selectedKeys: Set<string>
  onToggleSelect: (key: string) => void
}

export function CatalogAreaSection({
  area,
  stats,
  parameters,
  open,
  onToggle,
  selectedKeys,
  onToggleSelect,
}: CatalogAreaSectionProps) {
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
          <p className="mt-0.5 text-sm text-slate-600">{area.description_it}</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-slate-600">
          <span className="rounded-lg bg-slate-100 px-2 py-1 font-medium text-slate-800">
            Parametri: {stats.total}
          </span>
          <span className="rounded-lg bg-emerald-50 px-2 py-1 font-medium text-emerald-900">
            v0.4 (usato/indir.): {stats.v04UsedOrIndirect}
          </span>
          <span className="rounded-lg bg-violet-50 px-2 py-1 font-medium text-violet-900">
            Implementati: {stats.implementedLike}
          </span>
          <span className="rounded-lg bg-amber-50 px-2 py-1 font-medium text-amber-900">
            Da implementare: {stats.toImplementLike}
          </span>
          <span className="rounded-lg bg-slate-50 px-2 py-1 font-medium text-slate-700">{open ? '▼' : '▶'}</span>
        </div>
      </button>
      {open ? (
        <div id={panelId} role="region" aria-labelledby={btnId} className="space-y-3 border-t border-slate-100 px-4 py-4 sm:px-5">
          {parameters.length === 0 ? (
            <p className="text-sm text-slate-500">Nessun parametro corrisponde ai filtri in questa area.</p>
          ) : (
            parameters.map((p) => (
              <CatalogParameterCard
                key={p.key}
                param={p}
                selected={selectedKeys.has(p.key)}
                onToggleSelect={onToggleSelect}
              />
            ))
          )}
        </div>
      ) : null}
    </section>
  )
}
