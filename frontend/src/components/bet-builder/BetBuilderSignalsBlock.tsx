import type { BetBuilderSignalsEvidence } from '../../lib/cecchinoBetBuilderApi'
import type { ReactNode } from 'react'

type Props = {
  signals: BetBuilderSignalsEvidence
  marketKey: string
  compact?: boolean
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
      <div className="space-y-0.5">
        <p
          className={
            compact ? 'text-xs font-semibold text-slate-900' : 'text-sm font-semibold text-slate-900'
          }
        >
          Segnale diretto
        </p>
        {columns ? (
          <p className={compact ? 'text-xs text-slate-700' : 'text-sm text-slate-700'}>
            {columns} · SI
          </p>
        ) : null}
      </div>
    )
  } else if (signals.evidence_mode === 'derived_from_draw_consensus') {
    body = (
      <div className="space-y-0.5">
        <p
          className={
            compact ? 'text-xs font-semibold text-slate-900' : 'text-sm font-semibold text-slate-900'
          }
        >
          Derivato dal consenso X
        </p>
        {signals.yes_count > 0 || signals.required_count > 0 ? (
          <p
            className={
              compact
                ? 'text-xs tabular-nums text-slate-800'
                : 'text-sm tabular-nums text-slate-800'
            }
          >
            {signals.yes_count} / {denom} SI
            {columns ? <span className="text-slate-600"> · {columns}</span> : null}
          </p>
        ) : null}
      </div>
    )
  } else if (compact) {
    body = (
      <p className="text-xs tabular-nums text-slate-800">
        Segnali {signals.yes_count}/{denom}
        {columns ? <span className="text-slate-600"> · {columns}</span> : null}
      </p>
    )
  } else {
    body = (
      <div className="space-y-0.5">
        <p className="text-lg font-semibold tabular-nums text-slate-900">
          {signals.yes_count} / {denom} SI
        </p>
        {columns ? <p className="text-sm text-slate-700">{columns}</p> : null}
      </div>
    )
  }

  return (
    <section
      aria-label={`Segnali Cecchino ${marketKey}`}
      className={compact ? 'space-y-1' : 'space-y-2'}
      data-testid={compact ? 'signals-compact' : undefined}
    >
      {!compact ? (
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Segnali Cecchino
        </h3>
      ) : null}
      {body}
    </section>
  )
}
