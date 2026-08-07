import type { BetBuilderSignalsEvidence } from '../../lib/cecchinoBetBuilderApi'
import type { ReactNode } from 'react'

type Props = {
  signals: BetBuilderSignalsEvidence
  marketKey: string
  compact?: boolean
}

function isFiniteCount(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value)
}

function ConsensusDots({ yesCount, available }: { yesCount: number; available: number }) {
  const n = Math.max(0, available)
  if (n <= 0) return null
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

function ConsensusCountLine({
  signals,
  columnsInline = false,
}: {
  signals: BetBuilderSignalsEvidence
  columnsInline?: boolean
}) {
  const columns = signals.yes_columns?.length ? signals.yes_columns.join(' · ') : null
  const hasAvailable = isFiniteCount(signals.available_count)
  const countText = hasAvailable
    ? `${signals.yes_count} / ${signals.available_count} SI`
    : `${signals.yes_count} SI`

  return (
    <p className="text-sm font-semibold tabular-nums text-slate-800">
      {countText}
      {columnsInline && columns ? (
        <span className="font-medium text-slate-600"> · {columns}</span>
      ) : null}
    </p>
  )
}

function ConsensusThreshold({ required }: { required: number | null | undefined }) {
  if (!isFiniteCount(required)) return null
  return <p className="text-xs text-slate-500">Soglia ≥{required}</p>
}

function ConsensusFailedNote({ passed }: { passed: boolean }) {
  if (passed) return null
  return <p className="text-xs font-medium text-amber-700">Consenso non raggiunto</p>
}

function ConsensusBody({
  signals,
  title,
  columnsInline = false,
}: {
  signals: BetBuilderSignalsEvidence
  title?: string
  columnsInline?: boolean
}) {
  const columns = signals.yes_columns?.length ? signals.yes_columns.join(' · ') : null
  const hasAvailable = isFiniteCount(signals.available_count)

  return (
    <div className="space-y-1.5">
      {title ? <p className="text-xs font-semibold text-slate-900">{title}</p> : null}
      {hasAvailable ? (
        <ConsensusDots yesCount={signals.yes_count} available={signals.available_count} />
      ) : null}
      <ConsensusCountLine signals={signals} columnsInline={columnsInline} />
      {!columnsInline && columns ? (
        <p className="break-words text-xs font-medium text-slate-600">{columns}</p>
      ) : null}
      <ConsensusThreshold required={signals.required_count} />
      <ConsensusFailedNote passed={signals.passed === true} />
      {hasAvailable ? (
        <p className="sr-only">
          Segnali {signals.yes_count}/{signals.available_count}
        </p>
      ) : (
        <p className="sr-only">Segnali {signals.yes_count}</p>
      )}
    </div>
  )
}

export function BetBuilderSignalsBlock({ signals, marketKey, compact = false }: Props) {
  const columns = signals.yes_columns?.length ? signals.yes_columns.join(' · ') : null

  let body: ReactNode
  if (!signals.available) {
    body = (
      <p className={compact ? 'text-xs text-slate-600' : 'text-sm text-slate-600'}>
        Segnali non disponibili per questo mercato
      </p>
    )
  } else if (signals.evidence_mode === 'direct_single_formula') {
    body = (
      <div className="min-w-0 max-w-full space-y-1">
        <p className="text-xs font-semibold text-slate-900">Segnale diretto</p>
        {columns ? (
          <p className="break-words text-sm font-semibold tabular-nums text-slate-800">
            {columns} · SI
          </p>
        ) : null}
      </div>
    )
  } else if (signals.evidence_mode === 'derived_from_draw_consensus') {
    // Mobile-first: colonne su riga separata (niente columnsInline) per evitare compressione.
    body = <ConsensusBody signals={signals} title="Derivato dal consenso X" />
  } else {
    body = <ConsensusBody signals={signals} />
  }

  return (
    <section
      aria-label={`Segnali Cecchino ${marketKey}`}
      className="min-w-0 max-w-full space-y-1"
      data-testid={compact ? 'signals-compact' : 'signals-block'}
    >
      <h3 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
        Segnali
      </h3>
      {body}
    </section>
  )
}
