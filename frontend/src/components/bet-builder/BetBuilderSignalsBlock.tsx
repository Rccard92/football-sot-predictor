import type { BetBuilderSignalsEvidence } from '../../lib/cecchinoBetBuilderApi'
import type { ReactNode } from 'react'

type Props = {
  signals: BetBuilderSignalsEvidence
  marketKey: string
  compact?: boolean
}

function ConsensusDots({
  yesCount,
  required,
}: {
  yesCount: number
  required: number
}) {
  const n = Math.max(1, required || 4)
  return (
    <div className="flex items-center gap-1" aria-hidden>
      {Array.from({ length: n }, (_, i) => {
        const on = i < yesCount
        return (
          <span
            key={i}
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              on ? 'bg-slate-800' : 'bg-slate-200'
            }`}
            data-signal={on ? 'yes' : 'no'}
          />
        )
      })}
    </div>
  )
}

export function BetBuilderSignalsBlock({ signals, marketKey, compact = false }: Props) {
  const columns = signals.yes_columns?.length ? signals.yes_columns.join(' · ') : null
  const denom = signals.required_count || signals.available_count || 4

  let body: ReactNode
  if (!signals.available) {
    body = (
      <p className={compact ? 'text-xs text-slate-600' : 'text-sm text-slate-600'}>
        Segnali non disponibili per questo mercato
      </p>
    )
  } else if (signals.evidence_mode === 'direct_single_formula') {
    body = (
      <div className="space-y-1">
        <p className="text-xs font-semibold text-slate-900">Segnale diretto</p>
        {columns ? (
          <p className="text-sm font-semibold tabular-nums text-slate-800">
            {columns} · SI
          </p>
        ) : null}
      </div>
    )
  } else if (signals.evidence_mode === 'derived_from_draw_consensus') {
    body = (
      <div className="space-y-1.5">
        <p className="text-xs font-semibold text-slate-900">Derivato dal consenso X</p>
        <ConsensusDots yesCount={signals.yes_count} required={denom} />
        <p className="text-sm font-semibold tabular-nums text-slate-800">
          {signals.yes_count} / {denom} SI
          {columns ? <span className="font-medium text-slate-600"> · {columns}</span> : null}
        </p>
      </div>
    )
  } else {
    body = (
      <div className="space-y-1.5">
        <ConsensusDots yesCount={signals.yes_count} required={denom} />
        <p className="text-sm font-semibold tabular-nums text-slate-900">
          {signals.yes_count} / {denom} SI
        </p>
        <p className="sr-only">
          Segnali {signals.yes_count}/{denom}
        </p>
        {columns ? <p className="text-xs font-medium text-slate-600">{columns}</p> : null}
      </div>
    )
  }

  return (
    <section
      aria-label={`Segnali Cecchino ${marketKey}`}
      className="space-y-1"
      data-testid={compact ? 'signals-compact' : 'signals-block'}
    >
      <h3 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
        Segnali
      </h3>
      {body}
    </section>
  )
}
