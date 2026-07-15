import type { DrawCredibilityLeagueStability } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  league: DrawCredibilityLeagueStability
  /** @deprecated preferire i KPI interni a league */
  marketSummary?: { league_count: number; country_count: number }
}

function fmt(n: number | null | undefined, digits = 1): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function wilsonTxt(ci?: { lower_pct?: number | null; upper_pct?: number | null }): string {
  if (!ci || typeof ci.lower_pct !== 'number' || typeof ci.upper_pct !== 'number') return '—'
  return `${ci.lower_pct.toFixed(1)}–${ci.upper_pct.toFixed(1)}%`
}

function ShareBar({ pct }: { pct: number | null | undefined }) {
  const w = typeof pct === 'number' ? Math.max(0, Math.min(100, pct)) : 0
  return (
    <div className="mt-1 h-1.5 w-full rounded-full bg-slate-100">
      <div className="h-1.5 rounded-full bg-violet-500" style={{ width: `${w}%` }} />
    </div>
  )
}

export function DrawCredibilityLeagueStabilityPanel({ league }: Props) {
  const rows = league.leagues ?? []

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Stabilità per lega</h3>

      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-lg border border-slate-100 px-3 py-2 text-xs">
          <p className="text-[10px] uppercase text-slate-500">Leghe</p>
          <p className="text-sm font-semibold tabular-nums text-slate-900">{league.league_count}</p>
        </div>
        <div className="rounded-lg border border-slate-100 px-3 py-2 text-xs">
          <p className="text-[10px] uppercase text-slate-500">Share top 5</p>
          <p className="text-sm font-semibold tabular-nums text-slate-900">
            {fmt(league.top_5_share_pct)}%
          </p>
          <ShareBar pct={league.top_5_share_pct} />
        </div>
        <div className="rounded-lg border border-slate-100 px-3 py-2 text-xs">
          <p className="text-[10px] uppercase text-slate-500">Share top 10</p>
          <p className="text-sm font-semibold tabular-nums text-slate-900">
            {fmt(league.top_10_share_pct)}%
          </p>
          <ShareBar pct={league.top_10_share_pct} />
        </div>
        <div className="rounded-lg border border-slate-100 px-3 py-2 text-xs">
          <p className="text-[10px] uppercase text-slate-500">HHI / concentrazione</p>
          <p className="text-sm font-semibold tabular-nums text-slate-900">
            {typeof league.hhi === 'number' ? league.hhi.toFixed(4) : '—'}
          </p>
          <p className="text-[11px] text-slate-600">{league.concentration_status}</p>
        </div>
        <div className="rounded-lg border border-slate-100 px-3 py-2 text-xs">
          <p className="text-[10px] uppercase text-slate-500">Leghe affidabili</p>
          <p className="text-sm font-semibold tabular-nums text-slate-900">
            {league.reliable_league_count}
          </p>
          <p className="text-[11px] text-slate-600">
            Fragmented: {league.fragmented_leagues ? 'Sì' : 'No'}
          </p>
        </div>
      </div>

      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-violet-700">
        Top leghe
      </h4>
      {rows.length === 0 ? (
        <p className="text-xs text-slate-500">Nessuna riga per lega.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="border-b border-slate-200 text-slate-500">
              <tr>
                <th className="px-2 py-2 text-left">Paese</th>
                <th className="px-2 py-2 text-left">Lega</th>
                <th className="px-2 py-2 text-left">N</th>
                <th className="px-2 py-2 text-left">% dataset</th>
                <th className="px-2 py-2 text-left">Draw %</th>
                <th className="px-2 py-2 text-left">Wilson CI</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={`${r.country_name}__${r.league_name}`}
                  className="border-b border-slate-100"
                >
                  <td className="px-2 py-1.5">{r.country_name}</td>
                  <td className="px-2 py-1.5 font-medium text-slate-800">{r.league_name}</td>
                  <td className="px-2 py-1.5 tabular-nums">{r.rows}</td>
                  <td className="px-2 py-1.5 tabular-nums">{fmt(r.percentage_dataset)}%</td>
                  <td className="px-2 py-1.5 tabular-nums">{fmt(r.draw_rate_pct)}</td>
                  <td className="px-2 py-1.5 tabular-nums">{wilsonTxt(r.wilson_ci_95)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {league.note ? <p className="mt-2 text-[11px] text-slate-500">{league.note}</p> : null}
    </section>
  )
}
