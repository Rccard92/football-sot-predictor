import type {
  BalanceReadinessGate,
  BalanceReadinessGatesPayload,
} from '../../../lib/cecchinoModuleMonitoringApi'
import { MonitoringGateCard } from '../MonitoringGateCard'
import { balanceGateStateFromStatus, CARD_BASE } from '../moduleMonitoringUi'

type Props = {
  gates: BalanceReadinessGatesPayload | null
}

function valueLabel(gate: BalanceReadinessGate): string {
  if (gate.numerator != null && gate.denominator != null) {
    return `${gate.numerator} / ${gate.denominator}`
  }
  if (gate.value != null) return String(gate.value)
  return '—'
}

function GateSection({ title, items }: { title: string; items: BalanceReadinessGate[] }) {
  if (items.length === 0) return null
  return (
    <div className="space-y-3">
      <h5 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h5>
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((gate) => {
          const state = balanceGateStateFromStatus(gate.status)
          const num = gate.numerator
          const den = gate.denominator
          const progress =
            typeof num === 'number' && typeof den === 'number' && den > 0
              ? Math.min(1, num / den)
              : gate.status === 'pass'
                ? 1
                : null

          return (
            <MonitoringGateCard
              key={`${gate.category || 'g'}-${gate.key}`}
              title={gate.label_it || gate.key}
              valueLabel={valueLabel(gate)}
              thresholdLabel={gate.threshold != null ? String(gate.threshold) : undefined}
              progress={progress}
              state={state}
              explanation={
                gate.reason_codes && gate.reason_codes.length > 0
                  ? gate.reason_codes.join(' · ')
                  : undefined
              }
            />
          )
        })}
      </div>
    </div>
  )
}

export function BalanceReadinessGateMatrix({ gates }: Props) {
  const technical = gates?.technical?.gates || []
  const scientific = gates?.scientific?.gates || []

  if (technical.length === 0 && scientific.length === 0) {
    return (
      <div className={`${CARD_BASE} p-4`}>
        <h4 className="text-sm font-semibold text-slate-800">Gate di readiness</h4>
        <p className="mt-2 text-sm text-slate-600">
          Nessun gate disponibile per il periodo selezionato.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <h4 className="text-sm font-semibold text-slate-800">Gate di readiness</h4>
        <p className="text-xs text-slate-500">
          Tecnici e scientifici restano separati. I gate promozionali usano solo la coorte
          prospettica.
        </p>
      </div>
      <GateSection title="Gate tecnici" items={technical} />
      <GateSection title="Gate scientifici (prospective)" items={scientific} />
    </div>
  )
}
