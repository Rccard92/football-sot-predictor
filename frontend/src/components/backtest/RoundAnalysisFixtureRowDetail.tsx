import type { RoundAnalysisFixtureRow } from '../../lib/api'
import { errorCodeLabelIt, MODEL_KEYS } from './roundAnalysisUtils'

type Props = {
  fixture: RoundAnalysisFixtureRow
}

export function RoundAnalysisFixtureRowDetail({ fixture }: Props) {
  const expl = fixture.explanation_json?.[MODEL_KEYS.v21] as
    | Record<string, unknown>
    | undefined

  return (
    <div className="space-y-3 text-xs text-slate-700">
      {fixture.status === 'failed' ? (
        <p className="text-rose-700">{fixture.error_message ?? 'Errore calcolo'}</p>
      ) : null}
      {Object.entries(fixture.models_json).map(([key, block]) => (
        <div key={key} className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="font-semibold text-slate-900">{block.label ?? key}</div>
          <p className="text-[10px] text-slate-500">
            Richiesto: {block.model_version_requested ?? key} · Usato:{' '}
            {block.model_version_used ?? '—'} · Engine: {block.model_engine_name ?? '—'}
          </p>
          <p className="text-[10px] text-slate-500">
            Status: {block.model_status ?? block.status ?? '—'}
            {block.error_code
              ? ` · ${errorCodeLabelIt(block.error_code)} (${block.error_code})`
              : ''}
          </p>
          {block.status === 'error' ? (
            <p className="text-rose-700">{block.error_message ?? block.message ?? 'Errore tecnico'}</p>
          ) : null}
          {block.status === 'no_prediction' ? (
            <p className="text-slate-600">
              ND — {block.error_message ?? block.message ?? 'Nessuna predizione'}
            </p>
          ) : (
            <p>
              Previsto: {block.predicted_home_sot ?? '—'} / {block.predicted_away_sot ?? '—'} (tot{' '}
              {block.predicted_total_sot ?? '—'})
            </p>
          )}
          {block.status === 'ok' ? (
            <>
              <p>
                Aggressiva: linea {block.aggressive_line ?? '—'} · {block.aggressive_advice ?? '—'} —{' '}
                {block.aggressive_reason ?? ''}
              </p>
              <p>
                Cauta: linea {block.cautious_line ?? '—'} · {block.cautious_advice ?? '—'} —{' '}
                {block.cautious_reason ?? ''}
              </p>
            </>
          ) : null}
          {block.trace_summary &&
          typeof block.trace_summary === 'object' &&
          'missing_fields' in block.trace_summary ? (
            <p className="text-[10px] text-slate-500">
              Campi mancanti:{' '}
              {Array.isArray((block.trace_summary as { missing_fields?: string[] }).missing_fields)
                ? (block.trace_summary as { missing_fields: string[] }).missing_fields.join(', ')
                : '—'}
              {' · '}
              Prior:{' '}
              {(block.trace_summary as { prior_context?: { home_prior_matches?: number } }).prior_context
                ?.home_prior_matches ?? '—'}
              /
              {(block.trace_summary as { prior_context?: { away_prior_matches?: number } }).prior_context
                ?.away_prior_matches ?? '—'}
            </p>
          ) : null}
          {block.trace_summary ? (
            <details className="mt-1">
              <summary className="cursor-pointer text-slate-600">Trace modello</summary>
              <pre className="mt-1 max-h-32 overflow-auto rounded bg-slate-100 p-2 text-[10px]">
                {JSON.stringify(block.trace_summary, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      ))}
      {expl ? (
        <details>
          <summary className="cursor-pointer font-medium text-slate-800">
            Dettaglio macro v2.1
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-100 p-2 text-[10px]">
            {JSON.stringify(expl, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  )
}
