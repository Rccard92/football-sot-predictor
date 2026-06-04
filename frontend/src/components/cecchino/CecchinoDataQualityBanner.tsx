import type { CecchinoDataQuality } from '../../lib/cecchinoApi'
import {
  getLeakageStatus,
  hasLowSampleWarning,
  leakageDisplayLabel,
} from '../../lib/cecchinoUtils'

type Props = {
  dataQuality: CecchinoDataQuality | null | undefined
  calculationStatus?: string | null
}

export function CecchinoDataQualityBanner({ dataQuality, calculationStatus }: Props) {
  if (!dataQuality) return null

  const leakageStatus = getLeakageStatus(dataQuality)
  const leakageOk = leakageStatus === 'passed'
  const leakageFailed = leakageStatus === 'failed'
  const lowSample = hasLowSampleWarning(dataQuality.warnings)

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs">
      <span
        className={`rounded px-2 py-0.5 font-semibold uppercase ${
          leakageOk
            ? 'bg-emerald-100 text-emerald-800'
            : leakageFailed
              ? 'bg-red-100 text-red-800'
              : 'bg-slate-100 text-slate-600'
        }`}
      >
        LEAKAGE: {leakageDisplayLabel(leakageStatus)}
      </span>
      {calculationStatus && (
        <span className="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-700">
          Stato: {calculationStatus}
        </span>
      )}
      {lowSample && (
        <span className="rounded bg-amber-100 px-2 py-0.5 font-medium text-amber-900">
          Campione basso
        </span>
      )}
    </div>
  )
}
