import type {
  PredictiveAiAnalysisType,
  PredictiveAiOutput,
} from '../../lib/api'

const ANALYSIS_LABELS: Record<PredictiveAiAnalysisType, string> = {
  missed_high_non_extreme: 'High non estreme sottostimate',
  false_high_predictions: 'False high prediction',
  top3_model_comparison: 'Confronto top 3 modelli',
  single_fixture: 'Singola partita',
}

function severityClass(severity?: string) {
  if (severity === 'high') return 'bg-rose-100 text-rose-900'
  if (severity === 'low') return 'bg-slate-100 text-slate-700'
  return 'bg-amber-100 text-amber-900'
}

function formatReasonCodes(codes: string[] | string | undefined): string {
  if (!codes) return '—'
  if (Array.isArray(codes)) return codes.join(', ')
  return String(codes)
}

type Props = {
  output: PredictiveAiOutput | null | undefined
  analysisType?: string
}

export function PredictiveAiOutputView({ output, analysisType }: Props) {
  if (!output) return null

  const typeLabel =
    (analysisType && ANALYSIS_LABELS[analysisType as PredictiveAiAnalysisType]) ||
    output.analysis_type ||
    'Analisi'

  return (
    <div className="space-y-4 text-xs text-slate-800">
      <p className="text-[10px] uppercase tracking-wide text-violet-700">{typeLabel}</p>

      {output.short_verdict ? (
        <div className="rounded-lg border border-violet-200 bg-violet-50/50 p-3">
          <p className="text-sm font-semibold text-slate-900">{output.short_verdict}</p>
          {output.next_action ? (
            <p className="mt-2 text-slate-700">
              <span className="font-medium">Prossima azione:</span> {output.next_action}
            </p>
          ) : null}
        </div>
      ) : null}

      {output.key_evidence && output.key_evidence.length > 0 ? (
        <section>
          <h3 className="font-semibold text-slate-900">Evidenze numeriche</h3>
          <ul className="mt-2 space-y-2">
            {output.key_evidence.map((ev, i) => (
              <li key={i} className="rounded border border-slate-200 bg-white p-2">
                <span className="font-medium">{ev.metric}</span>: {ev.value}
                <p className="mt-1 text-slate-600">{ev.interpretation}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {output.root_causes && output.root_causes.length > 0 ? (
        <section>
          <h3 className="font-semibold text-slate-900">Cause radice</h3>
          <div className="mt-2 grid gap-2 lg:grid-cols-2">
            {output.root_causes.map((rc, i) => (
              <article key={i} className="rounded-lg border border-slate-200 bg-white p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="font-medium text-slate-900">{rc.cause}</h4>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ${severityClass(rc.severity)}`}>
                    {rc.severity ?? 'medium'}
                  </span>
                </div>
                <p className="mt-2 text-slate-700">{rc.evidence}</p>
                {rc.affected_models && rc.affected_models.length > 0 ? (
                  <p className="mt-1 text-slate-500">Modelli: {rc.affected_models.join(', ')}</p>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {output.recommended_experiments && output.recommended_experiments.length > 0 ? (
        <section>
          <h3 className="font-semibold text-slate-900">Esperimenti consigliati</h3>
          <div className="mt-2 grid gap-2 lg:grid-cols-2">
            {output.recommended_experiments.map((exp, i) => (
              <article key={i} className="rounded-lg border border-teal-200 bg-teal-50/30 p-3">
                <h4 className="font-medium text-teal-950">{exp.experiment_name}</h4>
                <p className="mt-1">
                  <span className="font-medium">Ipotesi:</span> {exp.hypothesis}
                </p>
                <p className="mt-1">
                  <span className="font-medium">Modifica da testare:</span> {exp.change_to_test}
                </p>
                <p className="mt-1">
                  <span className="font-medium">Beneficio atteso:</span> {exp.expected_benefit}
                </p>
                <p className="mt-1 text-amber-900">
                  <span className="font-medium">Rischio:</span> {exp.risk}
                </p>
                <p className="mt-1">
                  <span className="font-medium">Metrica di successo:</span> {exp.success_metric}
                </p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {output.do_not_overreact_to && output.do_not_overreact_to.length > 0 ? (
        <section>
          <h3 className="font-semibold text-slate-900">Non reagire eccessivamente a</h3>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-700">
            {output.do_not_overreact_to.map((item, i) => (
              <li key={i}>
                <span className="font-medium">{item.case}</span> — {item.reason}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {output.fixture_notes && output.fixture_notes.length > 0 ? (
        <section>
          <h3 className="font-semibold text-slate-900">Note fixture</h3>
          <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-700">
                <tr>
                  <th className="px-2 py-2">Match</th>
                  <th className="px-2 py-2">Pred</th>
                  <th className="px-2 py-2">Actual</th>
                  <th className="px-2 py-2">Errore</th>
                  <th className="px-2 py-2">Reason codes</th>
                  <th className="px-2 py-2">Diagnosi</th>
                </tr>
              </thead>
              <tbody>
                {output.fixture_notes.map((fn, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="px-2 py-2">{fn.match ?? '—'}</td>
                    <td className="px-2 py-2">{fn.predicted ?? '—'}</td>
                    <td className="px-2 py-2">{fn.actual ?? '—'}</td>
                    <td className="px-2 py-2">{fn.error ?? '—'}</td>
                    <td className="px-2 py-2">{formatReasonCodes(fn.reason_codes)}</td>
                    <td className="px-2 py-2">{fn.diagnosis ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  )
}

export { ANALYSIS_LABELS }
