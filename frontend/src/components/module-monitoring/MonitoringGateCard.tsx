import { MonitoringProgressRing } from './MonitoringProgressRing'
import { MonitoringStatusBadge } from './MonitoringStatusBadge'
import { CARD_BASE, type StatusTone } from './moduleMonitoringUi'

type GateState = 'superato' | 'in_raccolta' | 'bloccante' | 'non_valutabile'

const STATE_TONE: Record<GateState, StatusTone> = {
  superato: 'success',
  in_raccolta: 'collecting',
  bloccante: 'blocked',
  non_valutabile: 'unavailable',
}

const STATE_LABEL: Record<GateState, string> = {
  superato: 'Superato',
  in_raccolta: 'In attesa dati',
  bloccante: 'Bloccante',
  non_valutabile: 'Non valutabile',
}

type Props = {
  title: string
  valueLabel: string
  thresholdLabel?: string
  progress?: number | null
  state: GateState
  explanation?: string
}

export function MonitoringGateCard({
  title,
  valueLabel,
  thresholdLabel,
  progress,
  state,
  explanation,
}: Props) {
  return (
    <div className={`${CARD_BASE} flex gap-3 p-4`}>
      <MonitoringProgressRing
        value={state === 'non_valutabile' || state === 'in_raccolta' ? null : progress ?? null}
        color={state === 'bloccante' ? '#e11d48' : state === 'superato' ? '#059669' : '#0891b2'}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="text-sm font-semibold text-slate-800">{title}</h4>
          <MonitoringStatusBadge label={STATE_LABEL[state]} tone={STATE_TONE[state]} />
        </div>
        <p className="mt-1 text-sm tabular-nums text-slate-700">
          {valueLabel}
          {thresholdLabel ? (
            <span className="text-slate-500"> · soglia {thresholdLabel}</span>
          ) : null}
        </p>
        {explanation ? <p className="mt-1 text-xs text-slate-500">{explanation}</p> : null}
      </div>
    </div>
  )
}
