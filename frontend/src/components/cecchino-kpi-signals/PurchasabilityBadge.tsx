import type { KpiPurchasabilitySnapshot } from '../../lib/cecchinoKpiSignalsApi'

type Props = {
  snap?: KpiPurchasabilitySnapshot | null
  versionLabel: string
}

function statusText(snap?: KpiPurchasabilitySnapshot | null): string {
  if (!snap || snap.status === 'snapshot_unavailable' || snap.status == null) {
    return 'N/D'
  }
  if (snap.status === 'score_provisional') return 'Provvisorio'
  if (snap.status === 'gate_failed') return 'Non attivato'
  if (snap.status === 'non_calculable') return 'Non calcolabile'
  if (snap.status === 'unsupported_market') return 'Non supportato'
  if (snap.status === 'score') {
    const score = snap.score != null ? String(snap.score) : '—'
    const klass = snap.class_label || snap.class_key || ''
    return klass ? `${score} · ${klass}` : score
  }
  return snap.status
}

export function PurchasabilityBadge({ snap, versionLabel }: Props) {
  const tone =
    snap?.status === 'score'
      ? 'bg-emerald-50 text-emerald-800 ring-emerald-200'
      : snap?.status === 'score_provisional'
        ? 'bg-amber-50 text-amber-800 ring-amber-200'
        : snap?.status === 'unsupported_market' || snap?.status === 'gate_failed'
          ? 'bg-slate-100 text-slate-600 ring-slate-200'
          : 'bg-slate-50 text-slate-500 ring-slate-200'

  return (
    <span
      className={`inline-flex max-w-[11rem] items-center gap-1 truncate rounded-md px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-inset ${tone}`}
      title={`${versionLabel}: ${statusText(snap)}`}
    >
      <span className="font-semibold">{versionLabel}</span>
      <span className="truncate">{statusText(snap)}</span>
    </span>
  )
}
