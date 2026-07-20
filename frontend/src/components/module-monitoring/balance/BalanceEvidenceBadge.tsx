type Props = {
  status?: string | null
  scope?: string | null
}

const LABELS: Record<string, string> = {
  insufficient_data: 'Dati insufficienti',
  descriptive_only: 'Solo descrittivo',
  exploratory_evidence: 'Evidenza esplorativa',
  evidence_emerging: 'Evidenza emergente',
  evidence_inconsistent: 'Evidenza incoerente',
  not_evaluable: 'Non valutabile',
  historical_diagnostic: 'Storico diagnostico',
  prospective_persisted: 'Prospettico',
  mixed: 'Misto',
}

export function BalanceEvidenceBadge({ status, scope }: Props) {
  const s = status ? LABELS[status] || status.replace(/_/g, ' ') : '—'
  const sc = scope ? LABELS[scope] || scope.replace(/_/g, ' ') : null
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <span className="rounded-full bg-violet-100 px-2.5 py-1 font-medium text-violet-900">
        Evidenza: {s}
      </span>
      {sc ? (
        <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700">
          Scope: {sc}
        </span>
      ) : null}
    </div>
  )
}
