import type { BetBuilderBalanceContextPayload } from '../../lib/cecchinoBetBuilderApi'

type Props = {
  payload: BetBuilderBalanceContextPayload
  compact?: boolean
}

const PILLARS: Array<{
  key: 'f36' | 'dominance' | 'draw_credibility' | 'gap_coherence'
  label: string
}> = [
  { key: 'f36', label: 'Geometria' },
  { key: 'dominance', label: 'Dominance' },
  { key: 'draw_credibility', label: 'Credibilità X' },
  { key: 'gap_coherence', label: 'Coerenza 1/2' },
]

function fmtIndex(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, '')
}

export function BetBuilderBalanceContext({ payload, compact = false }: Props) {
  return (
    <section aria-label="Equilibrio vs Squilibrio v5" className={compact ? 'space-y-1.5' : 'space-y-3'}>
      <h3
        className={
          compact
            ? 'text-[10px] font-semibold uppercase tracking-wide text-slate-500'
            : 'text-xs font-semibold uppercase tracking-wide text-slate-500'
        }
      >
        Equilibrio vs Squilibrio v5
      </h3>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {PILLARS.map(({ key, label }) => {
          const pillar = payload.pillars?.[key]
          const index =
            pillar?.index ??
            (key === 'gap_coherence'
              ? payload.gap_coherence_index
              : key === 'f36'
                ? payload.f36_index
                : key === 'dominance'
                  ? payload.dominance_index
                  : payload.draw_credibility_index)
          const classLabel = pillar?.class_label ?? null
          return (
            <div
              key={key}
              className={
                compact
                  ? 'rounded-md border border-slate-100 bg-slate-50/60 px-2 py-1.5'
                  : 'rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2'
              }
              data-testid={`balance-pillar-${key}`}
            >
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                {label}
              </p>
              <p
                className={
                  compact
                    ? 'mt-0.5 text-xs font-semibold tabular-nums text-slate-900'
                    : 'mt-0.5 text-sm font-semibold tabular-nums text-slate-900'
                }
              >
                {fmtIndex(index)}
                {classLabel ? (
                  <span className="font-medium text-slate-600"> · {classLabel}</span>
                ) : null}
              </p>
            </div>
          )
        })}
      </div>
    </section>
  )
}
