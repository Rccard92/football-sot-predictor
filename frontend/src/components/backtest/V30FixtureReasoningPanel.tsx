import type { RoundAnalysisModelBlock } from '../../lib/api'
import { formatReasonCodes } from './roundAnalysisUtils'

const V30_NO_BET_COPY =
  'NO BET non significa pronostico perdente: indica che il value selector non ha trovato un pick con edge sufficiente. Solo i pick GIOCA con esito WIN o LOSS contano nelle statistiche.'

type TraceShape = {
  selection?: {
    decision?: string
    line?: number | null
    confidence_tier?: string
    profile?: string
    reason_codes?: string[]
    no_bet_reasons?: string[]
  }
  audit?: {
    actuals_used_as_input?: boolean
    leakage_guard?: boolean
  }
  v1_1_predicted_total?: number | null
  v2_1_predicted_total?: number | null
  prediction_gap?: number | null
  macro_snapshot?: Record<string, number | null | undefined>
}

function readTrace(block: RoundAnalysisModelBlock): TraceShape {
  const ts = block.trace_summary
  if (ts && typeof ts === 'object') {
    return ts as TraceShape
  }
  return {}
}

const MACRO_LABELS: Record<string, string> = {
  weighted_macro_multiplier_avg: 'Macro pesata',
  chance_quality_avg: 'Qualità occasioni',
  pace_control_avg: 'Ritmo/controllo',
  player_layer_avg: 'Player layer',
  lineups_avg: 'Formazioni',
  injuries_unavailable_avg: 'Infortuni/indisponibili',
  split_avg: 'Split casa/trasferta',
}

export function V30FixtureReasoningPanel({ block }: { block: RoundAnalysisModelBlock }) {
  const trace = readTrace(block)
  const selection = trace.selection ?? {}
  const audit = trace.audit ?? {}
  const decision = String(selection.decision ?? block.cautious_advice ?? '—')
  const line = selection.line ?? block.cautious_line
  const outcome = block.cautious_outcome
  const reasonCodes = [
    ...(selection.reason_codes ?? []),
    ...(selection.no_bet_reasons ?? []),
  ]
  const { display: reasonsDisplay, title: reasonsTitle } = formatReasonCodes(reasonCodes, 99)

  const gap =
    trace.prediction_gap ??
    (trace.v1_1_predicted_total != null && trace.v2_1_predicted_total != null
      ? Number(trace.v2_1_predicted_total) - Number(trace.v1_1_predicted_total)
      : null)

  const macros = trace.macro_snapshot ?? {}
  const macroEntries = Object.entries(MACRO_LABELS)
    .map(([key, label]) => {
      const v = macros[key]
      if (v == null) return null
      return (
        <li key={key}>
          {label}: {typeof v === 'number' ? v.toFixed(2) : String(v)}
        </li>
      )
    })
    .filter(Boolean)

  return (
    <section className="mt-3 rounded-lg border border-violet-200 bg-violet-50/40 p-3">
      <h4 className="text-xs font-semibold text-violet-900">Ragionamento v3.0 Value Selector</h4>
      <dl className="mt-2 grid gap-1 text-[11px] text-slate-800 sm:grid-cols-2">
        <div>
          <dt className="font-medium text-slate-600">Decisione</dt>
          <dd>
            {decision}
            {line != null ? ` · Over ${line}` : ''}
            {outcome ? ` · ${outcome}` : ''}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-600">Confidence tier</dt>
          <dd>{selection.confidence_tier ?? '—'}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-600">Profilo</dt>
          <dd>{selection.profile ?? '—'}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-600">v1.1 / v2.1 totale</dt>
          <dd>
            {trace.v1_1_predicted_total ?? '—'} / {trace.v2_1_predicted_total ?? '—'}
            {gap != null ? ` (gap ${gap >= 0 ? '+' : ''}${gap.toFixed(2)})` : ''}
          </dd>
        </div>
      </dl>
      <div className="mt-2 text-[11px]" title={reasonsTitle}>
        <span className="font-medium text-slate-600">Motivi: </span>
        {reasonsDisplay || '—'}
      </div>
      {macroEntries.length > 0 ? (
        <ul className="mt-2 list-inside list-disc text-[10px] text-slate-700">{macroEntries}</ul>
      ) : null}
      {Array.isArray(block.warnings) && block.warnings.length > 0 ? (
        <p className="mt-2 text-[10px] text-amber-800">Avvisi: {block.warnings.join(', ')}</p>
      ) : null}
      <p className="mt-2 text-[10px] text-slate-600">
        Audit: actuals_used_as_input=
        {String(audit.actuals_used_as_input ?? false)} · leakage_guard=
        {String(audit.leakage_guard ?? true)}
      </p>
      <p className="mt-2 text-[10px] leading-snug text-slate-500">{V30_NO_BET_COPY}</p>
    </section>
  )
}
