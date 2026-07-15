import { useMemo, useState } from 'react'
import type {
  DrawCredibilityInteractionBlock,
  DrawCredibilityInteractionCell,
} from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  interactions: DrawCredibilityInteractionBlock[]
  /** @deprecated non più usato come fallback categoriale */
  categorical?: Array<Record<string, unknown>>
}

type CellSource = 'primary' | 'sensitivity'

function fmt(n: number | null | undefined, digits = 1): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function wilsonTxt(ci: DrawCredibilityInteractionCell['wilson_ci_95']): string {
  if (!ci || typeof ci.lower_pct !== 'number' || typeof ci.upper_pct !== 'number') return '—'
  return `${ci.lower_pct.toFixed(1)}–${ci.upper_pct.toFixed(1)}%`
}

export function DrawCredibilityInteractionPanel({ interactions }: Props) {
  const [selectedKey, setSelectedKey] = useState<string>(interactions[0]?.interaction_key ?? '')
  const [source, setSource] = useState<CellSource>('primary')

  const selected = useMemo(() => {
    if (interactions.length === 0) return null
    return interactions.find((i) => i.interaction_key === selectedKey) ?? interactions[0]
  }, [interactions, selectedKey])

  const cells: DrawCredibilityInteractionCell[] = useMemo(() => {
    if (!selected) return []
    return source === 'primary' ? selected.primary_cells ?? [] : selected.sensitivity_cells ?? []
  }, [selected, source])

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Analisi interazioni</h3>

      {interactions.length === 0 ? (
        <p className="text-xs text-slate-500">Nessuna interazione calcolata su questo campione.</p>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <label className="text-xs text-slate-600" htmlFor="ix-select">
              Interazione
            </label>
            <select
              id="ix-select"
              className="min-w-[14rem] flex-1 rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
              value={selected?.interaction_key ?? ''}
              onChange={(e) => setSelectedKey(e.target.value)}
            >
              {interactions.map((ix) => (
                <option key={ix.interaction_key} value={ix.interaction_key}>
                  {ix.label || ix.interaction_key}
                </option>
              ))}
            </select>
            <div className="inline-flex rounded-lg border border-violet-200 bg-violet-50/50 p-0.5 text-xs">
              <button
                type="button"
                className={`rounded-md px-2.5 py-1 ${
                  source === 'primary' ? 'bg-violet-600 text-white' : 'text-violet-800'
                }`}
                onClick={() => setSource('primary')}
              >
                Primary
              </button>
              <button
                type="button"
                className={`rounded-md px-2.5 py-1 ${
                  source === 'sensitivity' ? 'bg-violet-600 text-white' : 'text-violet-800'
                }`}
                onClick={() => setSource('sensitivity')}
              >
                Sensitivity
              </button>
            </div>
          </div>

          {selected ? (
            <p className="mb-2 text-[11px] text-slate-500">
              {selected.row_dimension} × {selected.column_dimension}
              {selected.boundary_source ? ` · boundary: ${selected.boundary_source}` : ''}
              {selected.summary
                ? ` · celle affidabili Primary: ${String(selected.summary.primary_reliable_cells ?? '—')}`
                : ''}
            </p>
          ) : null}

          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="px-2 py-2 text-left">Riga</th>
                  <th className="px-2 py-2 text-left">Colonna</th>
                  <th className="px-2 py-2 text-left">N</th>
                  <th className="px-2 py-2 text-left">Pareggi</th>
                  <th className="px-2 py-2 text-left">Draw %</th>
                  <th className="px-2 py-2 text-left">Lift pp</th>
                  <th className="px-2 py-2 text-left">Wilson CI</th>
                  <th className="px-2 py-2 text-left">Stato</th>
                </tr>
              </thead>
              <tbody>
                {cells.map((c) => {
                  const suppressed = Boolean(c.suppressed)
                  return (
                    <tr
                      key={`${c.row_category}__${c.column_category}`}
                      className={`border-b border-slate-100 ${suppressed ? 'bg-slate-50/80 text-slate-400' : ''}`}
                    >
                      <td className="px-2 py-1.5">{c.row_category}</td>
                      <td className="px-2 py-1.5">{c.column_category}</td>
                      <td className="px-2 py-1.5 tabular-nums">{c.count}</td>
                      <td className="px-2 py-1.5 tabular-nums">{c.draws}</td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {suppressed ? '—' : fmt(c.draw_rate_pct)}
                      </td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {suppressed ? '—' : fmt(c.lift_vs_baseline_pp)}
                      </td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {suppressed ? '—' : wilsonTxt(c.wilson_ci_95)}
                      </td>
                      <td className="px-2 py-1.5">
                        {suppressed
                          ? `Soppressa${c.suppression_reason ? ` (${c.suppression_reason})` : ''}`
                          : c.reliable
                            ? 'Affidabile'
                            : 'Non affidabile'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
