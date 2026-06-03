import type { RoundAnalysisModelBlock } from '../../lib/api'
import {
  formatV30TotalsDisplay,
  getV30HumanExplanation,
  getV30ReferenceTotals,
} from '../../lib/v30Explanation'

const V30_NO_BET_COPY =
  'NO BET non significa pronostico perdente: indica che il value selector non ha trovato un pick con edge sufficiente. La spiegazione descrive solo il contesto pre-match, non il risultato reale.'

type Props = {
  block: RoundAnalysisModelBlock
  explanationSlice?: Record<string, unknown> | null
}

export function V30FixtureReasoningPanel({ block, explanationSlice }: Props) {
  const human = getV30HumanExplanation(block)
  const trace = block.trace_summary as Record<string, unknown> | undefined
  const selection = (trace?.selection ?? {}) as {
    decision?: string
    line?: number | null
    confidence_tier?: string
    profile?: string
    reason_codes?: string[]
    no_bet_reasons?: string[]
  }
  const audit = (trace?.audit ?? {}) as {
    actuals_used_as_input?: boolean
    leakage_guard?: boolean
  }

  const decision = String(selection.decision ?? block.cautious_advice ?? '—')
  const line = selection.line ?? block.cautious_line
  const tier = selection.confidence_tier ?? block.confidence ?? '—'
  const totalsDisplay = formatV30TotalsDisplay(block, explanationSlice)
  const { v11, v21, gap } = getV30ReferenceTotals(block, explanationSlice)

  const techCodes = [
    ...(selection.reason_codes ?? []),
    ...(selection.no_bet_reasons ?? []),
  ]

  const dataUsed = human?.data_used ?? {}

  return (
    <section className="mt-3 rounded-lg border border-violet-200 bg-violet-50/40 p-4">
      <h4 className="text-sm font-semibold text-violet-900">
        Perché la v3.0 ha scelto questa decisione
      </h4>

      <dl className="mt-3 grid gap-2 text-xs text-slate-800 sm:grid-cols-2">
        <div>
          <dt className="font-medium text-slate-600">Decisione</dt>
          <dd className="font-medium">
            {decision}
            {line != null ? ` · Over ${line}` : ''}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-600">Linea</dt>
          <dd>{line ?? '—'}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-600">Confidence</dt>
          <dd>{tier}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-600">Profilo</dt>
          <dd>{selection.profile ?? '—'}</dd>
        </div>
      </dl>

      {human?.italian_text ? (
        <div className="mt-3">
          <p className="text-[11px] font-medium text-slate-600">Spiegazione</p>
          <p className="mt-1 text-sm leading-relaxed text-slate-800">{human.italian_text}</p>
        </div>
      ) : null}

      {human?.key_factors && human.key_factors.length > 0 ? (
        <div className="mt-3">
          <p className="text-[11px] font-medium text-emerald-800">Fattori positivi</p>
          <ul className="mt-1 list-inside list-disc text-xs text-slate-700">
            {human.key_factors.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {(human?.risk_reason || (human?.warning_notes && human.warning_notes.length > 0)) ? (
        <div className="mt-3">
          <p className="text-[11px] font-medium text-amber-800">Fattori di rischio</p>
          <ul className="mt-1 list-inside list-disc text-xs text-slate-700">
            {human.risk_reason ? <li>{human.risk_reason}</li> : null}
            {human.warning_notes?.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <details className="mt-3 rounded border border-slate-200 bg-white/80 p-2">
        <summary className="cursor-pointer text-[11px] font-medium text-slate-700">
          Dati usati (pre-match)
        </summary>
        <ul className="mt-2 space-y-0.5 text-[10px] text-slate-600">
          <li>v1.1 / v2.1 totale: {totalsDisplay}</li>
          {v11 != null && v21 != null && gap != null ? (
            <li>
              Gap v2.1 − v1.1: {gap >= 0 ? '+' : ''}
              {gap.toFixed(2)}
            </li>
          ) : null}
          {Object.entries(dataUsed).map(([k, v]) =>
            v != null ? (
              <li key={k}>
                {k}: {typeof v === 'number' ? v.toFixed(2) : String(v)}
              </li>
            ) : null,
          )}
        </ul>
        {techCodes.length > 0 ? (
          <p className="mt-2 text-[10px] text-slate-400" title={techCodes.join(', ')}>
            Codici tecnici (debug): {techCodes.join(', ')}
          </p>
        ) : null}
      </details>

      <p className="mt-3 text-[10px] text-slate-600">
        Audit: actuals_used_as_input=
        {String(audit.actuals_used_as_input ?? false)} · leakage_guard=
        {String(audit.leakage_guard ?? true)}
      </p>
      <p className="mt-2 text-[10px] leading-snug text-slate-500">{V30_NO_BET_COPY}</p>
    </section>
  )
}
