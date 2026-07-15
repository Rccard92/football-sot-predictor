import type { DrawCredibilityCandidatePattern } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  patterns: DrawCredibilityCandidatePattern[]
}

function fmt(n: number | null | undefined, digits = 1): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '—'
}

export function DrawCredibilityCandidatePatternsPanel({ patterns }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Pattern candidati</h3>
      {patterns.length === 0 ? (
        <p className="text-xs text-slate-500">
          Nessun pattern soddisfa i criteri minimi attuali.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="border-b border-slate-200 text-slate-500">
              <tr>
                <th className="px-2 py-2">Descrizione</th>
                <th className="px-2 py-2">N Prim.</th>
                <th className="px-2 py-2">Draw %</th>
                <th className="px-2 py-2">Lift pp</th>
                <th className="px-2 py-2">Δ vs Sens.</th>
                <th className="px-2 py-2">Stabilità</th>
                <th className="px-2 py-2">Evidenza</th>
              </tr>
            </thead>
            <tbody>
              {patterns.map((p) => (
                <tr key={p.pattern_key} className="border-b border-slate-100">
                  <td className="px-2 py-2 font-medium text-slate-800">{p.description}</td>
                  <td className="px-2 py-2 tabular-nums">{p.primary_count}</td>
                  <td className="px-2 py-2 tabular-nums">{fmt(p.primary_draw_rate_pct)}</td>
                  <td className="px-2 py-2 tabular-nums">{fmt(p.primary_lift_pp)}</td>
                  <td className="px-2 py-2 tabular-nums">{fmt(p.rate_delta_pp)}</td>
                  <td className="px-2 py-2">{p.stability_status ?? '—'}</td>
                  <td className="px-2 py-2">{p.evidence_status ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
