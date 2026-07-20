import type {
  BalanceProgressRatio,
  BalanceProspectiveProgress,
} from '../../../lib/cecchinoModuleMonitoringApi'
import { CARD_BASE } from '../moduleMonitoringUi'

type Props = {
  progress: BalanceProspectiveProgress | null
}

function RatioRow({ item }: { item: BalanceProgressRatio }) {
  const num = item.numerator ?? 0
  const den = item.denominator ?? 0
  const pct = den > 0 ? Math.min(100, (num / den) * 100) : 0
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-slate-600">{item.label_it || 'Rapporto'}</span>
        <span className="tabular-nums font-medium text-slate-800">
          {num} / {den}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full rounded-full bg-gradient-to-r from-violet-600 to-blue-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export function BalanceProspectiveProgressView({ progress }: Props) {
  if (!progress) {
    return (
      <div className={`${CARD_BASE} p-4`}>
        <h4 className="text-sm font-semibold text-slate-800">Progresso prospettico</h4>
        <p className="mt-2 text-sm text-slate-600">Dati progresso non disponibili.</p>
      </div>
    )
  }

  const ratios = Object.values(progress.ratios || {})

  return (
    <div className={`${CARD_BASE} p-4`}>
      <h4 className="text-sm font-semibold text-slate-800">Progresso prospettico</h4>
      <p className="mt-1 text-xs text-slate-500">
        Rapporti verso soglie policy (nessuna % unica di readiness). Pending:{' '}
        {progress.prospective_pending ?? 0}
      </p>

      <div className="mt-4 space-y-3">
        {ratios.map((r, i) => (
          <RatioRow key={`${r.label_it || i}`} item={r} />
        ))}
      </div>

      <p className="mt-4 text-xs text-slate-600">
        Revisione teorica più precoce:{' '}
        <span className="font-medium text-slate-800">
          {progress.earliest_theoretical_review_label_it ||
            progress.earliest_theoretical_review_at ||
            'non calcolabile'}
        </span>
      </p>
    </div>
  )
}
