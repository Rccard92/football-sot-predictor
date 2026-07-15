import type {
  DrawCredibilityBootstrapRoiCi,
  DrawCredibilityCandidatePattern,
} from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  patterns: DrawCredibilityCandidatePattern[]
}

function fmt(n: number | null | undefined, digits = 1): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function formatInterval(p: DrawCredibilityCandidatePattern): string {
  if (p.column_type !== 'quantile') return '—'
  const lo = p.column_lower_bound
  const hi = p.column_upper_bound
  if (typeof lo !== 'number' && typeof hi !== 'number') return '—'
  const loIncl = p.column_lower_inclusive !== false
  const hiIncl = p.column_upper_inclusive === true
  const left = typeof lo === 'number' ? `${loIncl ? '[' : '('}${fmt(lo, 4)}` : '(-∞'
  const right = typeof hi === 'number' ? `${fmt(hi, 4)}${hiIncl ? ']' : ')'}` : '+∞)'
  return `${left}, ${right}`
}

function roiCiTxt(ci: DrawCredibilityBootstrapRoiCi | null | undefined): string {
  if (!ci) return '—'
  const lo = ci.lower_pct ?? ci.lower ?? ci.ci_lower
  const hi = ci.upper_pct ?? ci.upper ?? ci.ci_upper
  if (typeof lo !== 'number' || typeof hi !== 'number') return '—'
  return `${lo.toFixed(2)}–${hi.toFixed(2)}%`
}

function boundarySourceLabel(src: string | undefined): string {
  if (src === 'primary') return 'Primary'
  if (src === 'market_subset') return 'Market subset'
  if (src === 'categorical') return 'Categoria'
  return src ?? '—'
}

export function DrawCredibilityCandidatePatternsPanel({ patterns }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Pattern candidati</h3>
      <p className="mb-3 text-[11px] text-slate-500">
        Soglie definite sulla coorte Primary e applicate senza ricalcolo al Market subset.
      </p>
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
                <th className="px-2 py-2">column_type</th>
                <th className="px-2 py-2">Bin</th>
                <th className="px-2 py-2">Intervallo numerico</th>
                <th className="px-2 py-2">Fonte soglie</th>
                <th className="px-2 py-2">N Prim.</th>
                <th className="px-2 py-2">Draw %</th>
                <th className="px-2 py-2">Lift pp</th>
                <th className="px-2 py-2">N Market</th>
                <th className="px-2 py-2">match_status</th>
                <th className="px-2 py-2">ROI Market</th>
                <th className="px-2 py-2">CI ROI</th>
                <th className="px-2 py-2">Affidabile</th>
                <th className="px-2 py-2">Stabilità</th>
                <th className="px-2 py-2">Evidenza</th>
              </tr>
            </thead>
            <tbody>
              {patterns.map((p) => {
                const marketMatched = p.market_rows_matched
                const noMarketMatch = marketMatched === 0
                return (
                  <tr key={p.pattern_key} className="border-b border-slate-100 align-top">
                    <td className="px-2 py-2 font-medium text-slate-800">
                      <div>{p.description}</div>
                      {noMarketMatch ? (
                        <p className="mt-1 text-[11px] font-normal text-amber-800">
                          Nessuna fixture Market corrisponde esattamente al pattern Primary.
                        </p>
                      ) : null}
                    </td>
                    <td className="px-2 py-2">{p.column_type ?? '—'}</td>
                    <td className="px-2 py-2 tabular-nums">
                      {typeof p.column_bin_index === 'number' ? p.column_bin_index : '—'}
                    </td>
                    <td className="px-2 py-2 tabular-nums">{formatInterval(p)}</td>
                    <td className="px-2 py-2">{boundarySourceLabel(p.boundary_source)}</td>
                    <td className="px-2 py-2 tabular-nums">{p.primary_count}</td>
                    <td className="px-2 py-2 tabular-nums">{fmt(p.primary_draw_rate_pct)}</td>
                    <td className="px-2 py-2 tabular-nums">{fmt(p.primary_lift_pp)}</td>
                    <td className="px-2 py-2 tabular-nums">
                      {typeof marketMatched === 'number' ? marketMatched : '—'}
                    </td>
                    <td className="px-2 py-2">{p.match_status ?? '—'}</td>
                    <td className="px-2 py-2 tabular-nums">
                      {typeof p.market_roi_pct === 'number'
                        ? `${p.market_roi_pct.toFixed(2)}%`
                        : '—'}
                    </td>
                    <td className="px-2 py-2 tabular-nums">{roiCiTxt(p.market_roi_ci)}</td>
                    <td className="px-2 py-2">
                      {p.market_roi_reliable == null
                        ? '—'
                        : p.market_roi_reliable
                          ? 'Sì'
                          : 'No'}
                    </td>
                    <td className="px-2 py-2">{p.stability_status ?? '—'}</td>
                    <td className="px-2 py-2">{p.evidence_status ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
