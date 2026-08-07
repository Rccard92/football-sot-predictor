import type { MonitoringVersion } from '../../../lib/cecchinoSignalsApi'
import {
  MONITORING_VERSION_V1,
  MONITORING_VERSION_V2,
} from '../../../lib/cecchinoSignalsApi'

type Props = {
  value: MonitoringVersion
  onChange: (version: MonitoringVersion) => void
}

export function SignalsMonitoringVersionSelector({ value, onChange }: Props) {
  const isV1 = value === MONITORING_VERSION_V1
  const isV2 = value === MONITORING_VERSION_V2

  return (
    <div className="space-y-2" data-testid="monitoring-version-selector">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
        Versione monitoraggio
      </p>
      <div
        role="radiogroup"
        aria-label="Versione monitoraggio"
        className="grid max-w-xl grid-cols-1 gap-2 min-[360px]:grid-cols-2"
      >
        <button
          type="button"
          role="radio"
          aria-checked={isV1}
          data-testid="monitoring-version-v1"
          onClick={() => onChange(MONITORING_VERSION_V1)}
          className={`min-h-[44px] rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-500 motion-reduce:transition-none ${
            isV1
              ? 'border-slate-400 bg-slate-100 ring-2 ring-slate-300'
              : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
          }`}
        >
          <span className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-slate-800">V1 · Base</span>
            {isV1 && (
              <span className="text-slate-600" aria-hidden="true">
                ✓
              </span>
            )}
          </span>
          <span className="mt-0.5 block text-xs text-slate-500">≥1 SI</span>
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={isV2}
          data-testid="monitoring-version-v2"
          onClick={() => onChange(MONITORING_VERSION_V2)}
          className={`min-h-[44px] rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 motion-reduce:transition-none ${
            isV2
              ? 'border-indigo-400 bg-indigo-50 ring-2 ring-indigo-300'
              : 'border-slate-200 bg-white hover:border-indigo-200 hover:bg-indigo-50/40'
          }`}
        >
          <span className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-indigo-950">V2 · Confermato</span>
            {isV2 && (
              <span className="text-indigo-600" aria-hidden="true">
                ✓
              </span>
            )}
          </span>
          <span className="mt-0.5 block text-xs text-indigo-700/80">≥2 SI stesso segno</span>
        </button>
      </div>
      <p
        className="text-xs text-slate-500"
        data-testid="monitoring-version-microcopy"
      >
        {isV1
          ? 'Include i segnali a valore anche con una sola conferma SI.'
          : 'Richiede almeno 2 conferme SI sullo stesso segno. 1 e 2 restano single-formula.'}
      </p>
    </div>
  )
}
