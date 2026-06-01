import type { RoundAnalysisFixtureRow } from '../../lib/api'
import { MODEL_KEYS } from './roundAnalysisUtils'

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
          {block.status === 'no_prediction' ? (
            <p className="text-slate-600">
              ND — {block.message ?? 'Storico insufficiente prima della partita.'}
            </p>
          ) : (
          <p>
            Previsto: {block.predicted_home_sot ?? '—'} / {block.predicted_away_sot ?? '—'} (tot{' '}
            {block.predicted_total_sot ?? '—'})
          </p>
          )}
          {block.status !== 'no_prediction' ? (
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
