import type { V4HowRow } from '../../lib/cecchinoV4Api'
import { capitalize, fmtDecimal } from './format'

type Props = {
  rows: V4HowRow[]
  homeTeam: string
  awayTeam: string
}

function Bar({ label, value, max, mean, tone }: { label: string; value: number; max: number; mean: number; tone: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  const meanPct = max > 0 ? Math.min(100, (mean / max) * 100) : 0
  return (
    <div className="grid grid-cols-[minmax(120px,1fr)_2fr_auto] items-center gap-3">
      <span className="truncate text-base text-slate-700">{label}</span>
      <div className="relative h-4 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
        <div
          className="absolute inset-y-0 w-0.5 bg-slate-700"
          style={{ left: `${meanPct}%` }}
          title="Media divisione"
        />
      </div>
      <span className="w-12 text-right text-base font-semibold tabular-nums text-slate-900">{fmtDecimal(value, 1)}</span>
    </div>
  )
}

/** Barre orizzontali per statistica: fatti e subiti per squadra contro la media della divisione. */
export function V4HowBars({ rows, homeTeam, awayTeam }: Props) {
  return (
    <div className="space-y-5">
      {rows.map((r) => {
        const values = [r.home_for, r.away_for, r.division_mean, r.home_against ?? 0, r.away_against ?? 0]
        const max = Math.max(...values) * 1.15
        return (
          <div key={r.stat} className="space-y-2" data-testid={`v4-how-${r.stat}`}>
            <p className="text-base font-semibold text-slate-900">
              {capitalize(r.label)} · media divisione {fmtDecimal(r.division_mean, 1)}
              {r.exam === 'non_superato' ? ' · solo descrittiva' : ''}
              {r.exam === 'in_attesa' ? ' · esame in attesa' : ''}
            </p>
            <Bar label={`${homeTeam} fatti`} value={r.home_for} max={max} mean={r.division_mean} tone="bg-blue-500" />
            {r.home_against != null ? (
              <Bar label={`${homeTeam} subiti`} value={r.home_against} max={max} mean={r.division_mean} tone="bg-blue-300" />
            ) : null}
            <Bar label={`${awayTeam} fatti`} value={r.away_for} max={max} mean={r.division_mean} tone="bg-violet-500" />
            {r.away_against != null ? (
              <Bar label={`${awayTeam} subiti`} value={r.away_against} max={max} mean={r.division_mean} tone="bg-violet-300" />
            ) : null}
          </div>
        )
      })}
      <p className="text-base text-slate-500">La linea scura su ogni barra è la media della divisione.</p>
    </div>
  )
}
