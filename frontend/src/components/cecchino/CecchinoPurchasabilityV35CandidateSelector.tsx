import type { CecchinoPurchasabilityV35CandidateKey } from '../../lib/cecchinoTodayApi'
import { bbOppTabIdle, bbOppTabScroll, bbOppTabSelected } from '../bet-builder/betBuilderStyles'
import {
  formatV35CandidateWeightsSubtitle,
  resolveV35CandidateRegistry,
  V35_CANDIDATE_KEYS,
  V35_CANDIDATE_LABELS,
} from './cecchinoPurchasabilityV35UiUtils'
import type { CecchinoPurchasabilityV35Snapshot } from '../../lib/cecchinoTodayApi'

type Props = {
  snapshot: CecchinoPurchasabilityV35Snapshot
  selectedCandidate: CecchinoPurchasabilityV35CandidateKey
  onSelect: (candidate: CecchinoPurchasabilityV35CandidateKey) => void
  panelId: string
}

export function CecchinoPurchasabilityV35CandidateSelector({
  snapshot,
  selectedCandidate,
  onSelect,
  panelId,
}: Props) {
  const registry = resolveV35CandidateRegistry(snapshot)

  return (
    <div className="space-y-2" data-testid="v35-candidate-selector">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Candidate</p>
      <div className={`${bbOppTabScroll} gap-2`} role="tablist" aria-label="Candidate V3.5">
        {V35_CANDIDATE_KEYS.map((key) => {
          const selected = selectedCandidate === key
          const entry = registry[key]
          const weightsSubtitle = formatV35CandidateWeightsSubtitle(entry)
          const badge = key === 'A' ? 'REFERENCE' : 'TEST'
          return (
            <button
              key={key}
              type="button"
              role="tab"
              id={`${panelId}-v35-candidate-${key}`}
              aria-selected={selected}
              aria-controls={`${panelId}-v35-market-panel`}
              data-testid={`v35-candidate-${key}`}
              data-selected={selected ? 'true' : 'false'}
              data-badge={badge}
              className={selected ? bbOppTabSelected : bbOppTabIdle}
              onClick={() => onSelect(key)}
            >
              <span className="flex flex-col items-start gap-0.5 text-left">
                <span className="flex items-center gap-1.5">
                  <span className="font-bold">{key}</span>
                  <span className="text-[10px] font-semibold uppercase tracking-wide opacity-80">
                    {badge}
                  </span>
                </span>
                <span className="text-[11px] font-medium">{V35_CANDIDATE_LABELS[key]}</span>
                {weightsSubtitle ? (
                  <span
                    className="text-[10px] font-normal opacity-70"
                    data-testid={`v35-candidate-weights-${key}`}
                  >
                    {weightsSubtitle}
                  </span>
                ) : null}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
