import type { DrawCredibilityTemporalStability } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  temporal: DrawCredibilityTemporalStability
}

const BLOCK_LABELS: Record<string, string> = {
  early: 'Early',
  middle: 'Middle',
  late: 'Late',
}

function fmt(n: number | null | undefined, digits = 1): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function wilsonTxt(ci?: { lower_pct?: number | null; upper_pct?: number | null }): string {
  if (!ci || typeof ci.lower_pct !== 'number' || typeof ci.upper_pct !== 'number') return '—'
  return `${ci.lower_pct.toFixed(1)}–${ci.upper_pct.toFixed(1)}%`
}

export function DrawCredibilityTemporalStabilityPanel({ temporal }: Props) {
  const weeks = temporal.iso_weeks ?? []
  const blocks = temporal.chronological_blocks ?? []

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Stabilità temporale</h3>

      {temporal.short_observation_window ? (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-xs text-amber-900">
          Finestra di osservazione breve ({temporal.time_span_days} giorni): la stabilità temporale
          va interpretata con cautela.
        </div>
      ) : (
        <p className="mb-3 text-xs text-slate-600">
          Periodo osservato: {temporal.time_span_days} giorni.
        </p>
      )}

      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-violet-700">
        Settimane ISO
      </h4>
      {weeks.length === 0 ? (
        <p className="mb-4 text-xs text-slate-500">Nessuna settimana ISO disponibile.</p>
      ) : (
        <div className="mb-4 overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="border-b border-slate-200 text-slate-500">
              <tr>
                <th className="px-2 py-2 text-left">Settimana</th>
                <th className="px-2 py-2 text-left">Da</th>
                <th className="px-2 py-2 text-left">A</th>
                <th className="px-2 py-2 text-left">N</th>
                <th className="px-2 py-2 text-left">Pareggi</th>
                <th className="px-2 py-2 text-left">Draw %</th>
                <th className="px-2 py-2 text-left">Wilson CI</th>
              </tr>
            </thead>
            <tbody>
              {weeks.map((w) => (
                <tr key={w.week_key} className="border-b border-slate-100">
                  <td className="px-2 py-1.5 font-medium text-slate-800">{w.week_key}</td>
                  <td className="px-2 py-1.5">{w.first_date ?? '—'}</td>
                  <td className="px-2 py-1.5">{w.last_date ?? '—'}</td>
                  <td className="px-2 py-1.5 tabular-nums">{w.rows}</td>
                  <td className="px-2 py-1.5 tabular-nums">{w.draws}</td>
                  <td className="px-2 py-1.5 tabular-nums">{fmt(w.draw_rate_pct)}</td>
                  <td className="px-2 py-1.5 tabular-nums">{wilsonTxt(w.wilson_ci_95)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-violet-700">
        Blocchi cronologici (early / middle / late)
      </h4>
      {blocks.length === 0 ? (
        <p className="text-xs text-slate-500">Nessun blocco cronologico disponibile.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="border-b border-slate-200 text-slate-500">
              <tr>
                <th className="px-2 py-2 text-left">Blocco</th>
                <th className="px-2 py-2 text-left">Da</th>
                <th className="px-2 py-2 text-left">A</th>
                <th className="px-2 py-2 text-left">N</th>
                <th className="px-2 py-2 text-left">Draw %</th>
                <th className="px-2 py-2 text-left">AUC (se presenti)</th>
              </tr>
            </thead>
            <tbody>
              {blocks.map((b) => {
                const aucs = b.feature_aucs ?? {}
                const aucParts = Object.entries(aucs)
                  .filter(([, v]) => typeof v === 'number')
                  .map(([k, v]) => `${k}: ${Number(v).toFixed(3)}`)
                return (
                  <tr key={b.block} className="border-b border-slate-100">
                    <td className="px-2 py-1.5 font-medium text-slate-800">
                      {BLOCK_LABELS[b.block] ?? b.block}
                    </td>
                    <td className="px-2 py-1.5">{b.date_from ?? '—'}</td>
                    <td className="px-2 py-1.5">{b.date_to ?? '—'}</td>
                    <td className="px-2 py-1.5 tabular-nums">{b.rows}</td>
                    <td className="px-2 py-1.5 tabular-nums">{fmt(b.draw_rate_pct)}</td>
                    <td className="px-2 py-1.5 text-slate-600">
                      {aucParts.length > 0 ? aucParts.join(' · ') : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {temporal.note ? <p className="mt-2 text-[11px] text-slate-500">{temporal.note}</p> : null}
    </section>
  )
}
