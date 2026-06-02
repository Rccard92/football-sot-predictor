import type { RoundAnalysisDetail } from '../../lib/api'
import { statusLabelIt } from './roundAnalysisUtils'

type Props = {
  detail: RoundAnalysisDetail
}

export function RoundAnalysisDetailBox({ detail }: Props) {
  const show =
    detail.status === 'failed' ||
    detail.status === 'completed_with_warnings' ||
    detail.error_json ||
    (detail.config_json && (detail.config_json as Record<string, unknown>)['merge_mode'])

  if (!show) return null

  const err = detail.error_json ?? {}
  const preflight =
    typeof err.preflight === 'object' && err.preflight !== null
      ? (err.preflight as Record<string, unknown>)
      : null

  const cfg = (detail.config_json ?? {}) as Record<string, unknown>
  const mergeMode = typeof cfg.merge_mode === 'string' ? cfg.merge_mode : null
  const updated = Array.isArray(cfg.models_calculated_last_run) ? (cfg.models_calculated_last_run as string[]) : []
  const preserved = Array.isArray(cfg.models_preserved_last_run) ? (cfg.models_preserved_last_run as string[]) : []

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-4 text-sm text-slate-800">
      <h3 className="font-semibold text-slate-900">Dettaglio analisi</h3>
      <dl className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-slate-500">Versione</dt>
          <dd>v{detail.analysis_version}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Stato</dt>
          <dd>{detail.status_label ?? statusLabelIt(detail.status)}</dd>
        </div>
        {mergeMode ? (
          <div>
            <dt className="text-slate-500">Modalità merge</dt>
            <dd>{mergeMode}</dd>
          </div>
        ) : null}
        <div>
          <dt className="text-slate-500">Qualità dati</dt>
          <dd>{detail.data_quality_status ?? detail.data_quality_summary_json?.badge ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Motivo</dt>
          <dd>{detail.status_reason ?? String(err.reason ?? '—')}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Fixture fallite</dt>
          <dd>{detail.failed_fixtures}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Modelli senza predizione</dt>
          <dd>{detail.failed_models_count}</dd>
        </div>
        {updated.length > 0 ? (
          <div className="sm:col-span-2">
            <dt className="text-slate-500">Modello aggiornato</dt>
            <dd>{updated.join(', ')}</dd>
          </div>
        ) : null}
        {preserved.length > 0 ? (
          <div className="sm:col-span-2">
            <dt className="text-slate-500">Modelli preservati</dt>
            <dd>{preserved.join(', ')}</dd>
          </div>
        ) : null}
        {preflight ? (
          <div className="sm:col-span-2">
            <dt className="text-slate-500">Storico (preflight)</dt>
            <dd>
              min prior casa {String(preflight.min_prior_matches_home)}, trasferta{' '}
              {String(preflight.min_prior_matches_away)}, media{' '}
              {String(preflight.avg_prior_matches)}
            </dd>
          </div>
        ) : null}
        {err.message ? (
          <div className="sm:col-span-2">
            <dt className="text-slate-500">Messaggio</dt>
            <dd>{String(err.message)}</dd>
          </div>
        ) : null}
      </dl>
    </div>
  )
}
