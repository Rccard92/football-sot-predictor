import type { BetBuilderSignalsEvidence } from '../../lib/cecchinoBetBuilderApi'
import type { ReactNode } from 'react'

type Props = {
  signals: BetBuilderSignalsEvidence
  marketKey: string
}

export function BetBuilderSignalsBlock({ signals, marketKey }: Props) {
  const columns = signals.yes_columns?.length ? signals.yes_columns.join(' · ') : null

  let body: ReactNode
  if (!signals.available) {
    body = (
      <p className="text-sm text-slate-600">Segnali non disponibili per questo mercato</p>
    )
  } else if (signals.evidence_mode === 'direct_single_formula') {
    body = (
      <div className="space-y-1">
        <p className="text-sm font-semibold text-slate-900">Segnale diretto</p>
        {columns ? <p className="text-sm text-slate-700">{columns} · SI</p> : null}
      </div>
    )
  } else if (signals.evidence_mode === 'derived_from_draw_consensus') {
    body = (
      <div className="space-y-1">
        <p className="text-sm font-semibold text-slate-900">Derivato dal consenso X</p>
        {signals.yes_count > 0 || signals.required_count > 0 ? (
          <p className="text-sm tabular-nums text-slate-800">
            {signals.yes_count} / {signals.required_count || signals.available_count || 4} SI
            {columns ? <span className="text-slate-600"> · {columns}</span> : null}
          </p>
        ) : null}
      </div>
    )
  } else {
    const denom = signals.required_count || signals.available_count || 4
    body = (
      <div className="space-y-1">
        <p className="text-lg font-semibold tabular-nums text-slate-900">
          {signals.yes_count} / {denom} SI
        </p>
        {columns ? <p className="text-sm text-slate-700">{columns}</p> : null}
      </div>
    )
  }

  return (
    <section aria-label={`Segnali Cecchino ${marketKey}`} className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Segnali Cecchino
      </h3>
      {body}
    </section>
  )
}
