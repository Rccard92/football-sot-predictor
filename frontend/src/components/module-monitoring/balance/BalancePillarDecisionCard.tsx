import type { BalanceReadinessPillar } from '../../../lib/cecchinoModuleMonitoringApi'
import { balanceDecisionLabelIt, CARD_BASE, STATUS_CLASSES, type StatusTone } from '../moduleMonitoringUi'

type Props = {
  title: string
  pillar: BalanceReadinessPillar
}

function evidenceTone(status: string | undefined): StatusTone {
  switch ((status || '').toLowerCase()) {
    case 'exploratory_evidence':
    case 'descriptive_only':
      return 'collecting'
    case 'evidence_inconsistent':
      return 'warning'
    case 'insufficient_data':
      return 'blocked'
    case 'ready_for_manual_review':
      return 'success'
    default:
      return 'unavailable'
  }
}

const EVIDENCE_LABELS: Record<string, string> = {
  descriptive_only: 'Solo descrittivo',
  exploratory_evidence: 'Evidenza esplorativa',
  evidence_inconsistent: 'Evidenza inconsistente',
  insufficient_data: 'Dati insufficienti',
}

const DECISION_LABELS: Record<string, string> = {
  descriptive_official: 'Descrittivo ufficiale',
  continue_monitoring: 'Continua monitoraggio',
  review_required: 'Revisione richiesta',
  insufficient_data: 'Dati insufficienti',
}

export function BalancePillarDecisionCard({ title, pillar }: Props) {
  const tone = evidenceTone(pillar.evidence_status)
  const evidenceLabel =
    EVIDENCE_LABELS[pillar.evidence_status || ''] ||
    pillar.evidence_status ||
    '—'
  const decisionLabel =
    DECISION_LABELS[pillar.decision || ''] ||
    balanceDecisionLabelIt(pillar.decision) ||
    pillar.decision ||
    '—'

  return (
    <div className={`${CARD_BASE} p-4`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h5 className="text-sm font-semibold text-slate-800">{title}</h5>
          {pillar.role_label ? (
            <p className="text-xs text-slate-500">{pillar.role_label}</p>
          ) : null}
        </div>
        <span
          className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[tone]}`}
        >
          {evidenceLabel}
        </span>
      </div>

      <dl className="mt-3 space-y-1 text-xs text-slate-600">
        <div className="flex justify-between gap-2">
          <dt>Decisione pilastro</dt>
          <dd className="font-medium text-slate-800">{decisionLabel}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Validazione prospettica</dt>
          <dd className="font-medium text-slate-800">
            {pillar.prospective_validation_status || '—'}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Uso Signals</dt>
          <dd className="font-medium text-slate-800">{pillar.signal_usage || 'blocked'}</dd>
        </div>
      </dl>

      {pillar.usage_note ? (
        <p className="mt-3 text-xs text-slate-600">{pillar.usage_note}</p>
      ) : null}

      {pillar.reason_codes && pillar.reason_codes.length > 0 ? (
        <p className="mt-2 text-xs text-amber-800">
          Reason codes: {pillar.reason_codes.join(' · ')}
        </p>
      ) : null}

      {pillar.warnings && pillar.warnings.length > 0 ? (
        <ul className="mt-2 space-y-1 text-xs text-slate-500">
          {pillar.warnings.map((w) => (
            <li key={w}>• {w}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
