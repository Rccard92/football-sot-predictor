import { v4Mono } from './constants'
import { fmtPct } from './format'

type Props = {
  matrix: number[][]
  maxGoals: number
  homeTeam: string
  awayTeam: string
}

/** Mappa compatta dei punteggi 0..max gol: celle a 12 px, piu' scuro = piu' probabile. */
export function V4ScoreMatrix({ matrix, maxGoals, homeTeam, awayTeam }: Props) {
  const size = Math.min(maxGoals + 1, matrix.length)
  if (size === 0) return null
  let peak = 0
  for (const row of matrix) for (const v of row) if (v > peak) peak = v

  return (
    <div className="space-y-1.5" data-testid="v4-score-matrix">
      <p className="text-xs text-slate-500">
        Righe: gol {homeTeam}. Colonne: gol {awayTeam}. Più scuro, più probabile.
      </p>
      <div className="overflow-x-auto">
        <div
          className="grid gap-0.5"
          style={{ gridTemplateColumns: `1.75rem repeat(${size}, minmax(2.5rem, 1fr))`, minWidth: `${1.75 + size * 2.5}rem` }}
          role="table"
          aria-label="Probabilità dei punteggi"
        >
          <div role="columnheader" aria-hidden />
          {Array.from({ length: size }, (_, a) => (
            <div key={`h${a}`} role="columnheader" className={`${v4Mono} text-center text-xs font-semibold text-slate-500`}>
              {a}
            </div>
          ))}
          {matrix.slice(0, size).map((row, h) => (
            <div key={`r${h}`} role="row" className="contents">
              <div role="rowheader" className={`${v4Mono} flex items-center justify-center text-xs font-semibold text-slate-500`}>
                {h}
              </div>
              {row.slice(0, size).map((p, a) => {
                const alpha = peak > 0 ? 0.08 + (p / peak) * 0.82 : 0
                return (
                  <div
                    key={`c${h}-${a}`}
                    role="cell"
                    className={`${v4Mono} flex h-7 items-center justify-center rounded text-xs text-slate-900`}
                    style={{ backgroundColor: `rgba(37, 99, 235, ${alpha.toFixed(2)})`, color: alpha > 0.55 ? '#fff' : undefined }}
                    aria-label={`${homeTeam} ${h} - ${awayTeam} ${a}: ${fmtPct(p)}`}
                  >
                    {fmtPct(p)}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
