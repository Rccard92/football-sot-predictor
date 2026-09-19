import { fmtPct } from './format'

type Props = {
  matrix: number[][]
  maxGoals: number
  homeTeam: string
  awayTeam: string
}

/** Mappa dei punteggi probabili 0..max gol, griglia CSS senza libreria grafica. */
export function V4ScoreMatrix({ matrix, maxGoals, homeTeam, awayTeam }: Props) {
  const size = Math.min(maxGoals + 1, matrix.length)
  if (size === 0) return null
  let peak = 0
  for (const row of matrix) for (const v of row) if (v > peak) peak = v

  return (
    <div className="space-y-2" data-testid="v4-score-matrix">
      <p className="text-base text-slate-700">
        Righe: gol {homeTeam}. Colonne: gol {awayTeam}. Più scuro, più probabile.
      </p>
      <div className="overflow-x-auto">
        <div
          className="grid gap-1"
          style={{ gridTemplateColumns: `3rem repeat(${size}, minmax(3.25rem, 1fr))`, minWidth: `${3 + size * 3.25}rem` }}
          role="table"
          aria-label="Probabilità dei punteggi"
        >
          <div role="columnheader" className="text-center text-base font-semibold text-slate-500" aria-hidden />
          {Array.from({ length: size }, (_, a) => (
            <div key={`h${a}`} role="columnheader" className="text-center text-base font-semibold text-slate-500">
              {a}
            </div>
          ))}
          {matrix.slice(0, size).map((row, h) => (
            <div key={`r${h}`} role="row" className="contents">
              <div role="rowheader" className="flex items-center justify-center text-base font-semibold text-slate-500">
                {h}
              </div>
              {row.slice(0, size).map((p, a) => {
                const alpha = peak > 0 ? 0.08 + (p / peak) * 0.82 : 0
                return (
                  <div
                    key={`c${h}-${a}`}
                    role="cell"
                    className="flex h-11 items-center justify-center rounded-md text-base tabular-nums text-slate-900"
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
