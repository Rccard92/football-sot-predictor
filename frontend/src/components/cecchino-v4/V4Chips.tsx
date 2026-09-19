import type {
  V4ChallengerStatus,
  V4ExamOutcome,
  V4LineupsStatus,
  V4PlayResult,
  V4ShortlistItemStatus,
  V4Verdict,
} from '../../lib/cecchinoV4Api'
import {
  V4_CHALLENGER_STATUS_CHIP,
  V4_CHALLENGER_STATUS_LABELS,
  V4_EXAM_OUTCOME_CHIP,
  V4_EXAM_OUTCOME_LABELS,
  V4_LINEUPS_DOT,
  V4_LINEUPS_LABELS,
  V4_PLAY_RESULT_CHIP,
  V4_PLAY_RESULT_LABELS,
  V4_SHORTLIST_STATUS_CHIP,
  V4_SHORTLIST_STATUS_LABELS,
  V4_VERDICT_CHIP,
  V4_VERDICT_LABELS,
  v4Chip,
} from './constants'

export function V4VerdictChip({ verdict, label }: { verdict: V4Verdict; label?: string | null }) {
  const cls = V4_VERDICT_CHIP[verdict] ?? V4_VERDICT_CHIP.prezzo_giusto
  return (
    <span className={`${v4Chip} ${cls}`} data-testid="v4-verdict-chip" data-verdict={verdict}>
      {label || V4_VERDICT_LABELS[verdict] || verdict}
    </span>
  )
}

export function V4ShortlistStatusChip({
  status,
  result,
}: {
  status: V4ShortlistItemStatus
  result: V4PlayResult | null
}) {
  if (status === 'regolata' && result) {
    return (
      <span className={`${v4Chip} ${V4_PLAY_RESULT_CHIP[result]}`} data-testid="v4-status-chip">
        {V4_PLAY_RESULT_LABELS[result]}
      </span>
    )
  }
  return (
    <span className={`${v4Chip} ${V4_SHORTLIST_STATUS_CHIP[status]}`} data-testid="v4-status-chip">
      {V4_SHORTLIST_STATUS_LABELS[status]}
    </span>
  )
}

export function V4ExamChip({ outcome }: { outcome: V4ExamOutcome }) {
  return (
    <span className={`${v4Chip} ${V4_EXAM_OUTCOME_CHIP[outcome]}`} data-testid="v4-exam-chip">
      {V4_EXAM_OUTCOME_LABELS[outcome]}
    </span>
  )
}

export function V4ChallengerChip({ status }: { status: V4ChallengerStatus }) {
  return (
    <span className={`${v4Chip} ${V4_CHALLENGER_STATUS_CHIP[status]}`}>
      {V4_CHALLENGER_STATUS_LABELS[status]}
    </span>
  )
}

export function V4LineupsDot({ status, withText = true }: { status: V4LineupsStatus; withText?: boolean }) {
  const label = V4_LINEUPS_LABELS[status]
  return (
    <span className="inline-flex items-center gap-2 text-base text-slate-600" title={label}>
      <span className={`inline-block h-3 w-3 shrink-0 rounded-full ${V4_LINEUPS_DOT[status]}`} aria-hidden />
      {withText ? label : <span className="sr-only">{label}</span>}
    </span>
  )
}
