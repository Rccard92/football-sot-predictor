import type { PredictiveRunListItem, PredictiveSimulationRun } from '../../lib/api'

type Props = {
  runs: PredictiveRunListItem[]
  loading: boolean
  currentRunId: number | null
  onOpenRun: (runId: number) => void
  onRefresh: () => void
}

export function PredictiveRunHistoryPanel({
  runs,
  loading,
  currentRunId,
  onOpenRun,
  onRefresh,
}: Props) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900">Storico analisi</h2>
        <button
          type="button"
          className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
          onClick={() => onRefresh()}
        >
          Aggiorna
        </button>
      </div>
      {loading ? <p className="mt-3 text-xs text-slate-600">Caricamento storico…</p> : null}
      {!loading && runs.length === 0 ? (
        <p className="mt-3 text-xs text-slate-600">Nessuna analisi salvata. Esegui un&apos;analisi per popolare lo storico.</p>
      ) : null}
      <ul className="mt-3 space-y-2">
        {runs.map((r) => (
          <li
            key={r.run_id}
            className={`flex flex-wrap items-center justify-between gap-2 rounded border px-3 py-2 text-xs ${
              currentRunId === r.run_id ? 'border-violet-400 bg-violet-50/50' : 'border-slate-200'
            }`}
          >
            <div>
              <p className="font-medium text-slate-900">
                Run #{r.run_id} · {r.season_label ?? r.season_year}
              </p>
              <p className="text-slate-600">
                {r.created_at ? new Date(r.created_at).toLocaleString('it-IT') : '—'} · {r.fixtures_count}{' '}
                fixture · {r.strategies_count} strategie
              </p>
              {r.main_warning ? (
                <p className="mt-1 text-amber-800">{r.main_warning}</p>
              ) : null}
              <p className="mt-1 text-slate-500">
                Consigliata: {r.recommended_strategy ?? '—'} · Best MAE: {r.best_mae_strategy ?? '—'}
              </p>
            </div>
            <button
              type="button"
              className="rounded border border-violet-700 px-3 py-1 text-violet-800 hover:bg-violet-50"
              onClick={() => onOpenRun(r.run_id)}
            >
              Apri analisi
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

type CurrentProps = {
  run: PredictiveSimulationRun | null
  savedMessage: string | null
}

export function PredictiveCurrentRunCard({ run, savedMessage }: CurrentProps) {
  if (!run && !savedMessage) return null
  const summary = run?.summary ?? {}
  return (
    <section className="rounded-lg border border-violet-200 bg-violet-50/40 p-4 text-xs">
      {savedMessage ? <p className="font-medium text-violet-900">{savedMessage}</p> : null}
      {run ? (
        <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <span className="text-slate-500">Run</span>
            <p className="font-medium text-slate-900">#{run.run_id}</p>
          </div>
          <div>
            <span className="text-slate-500">Data</span>
            <p className="font-medium text-slate-900">
              {run.created_at ? new Date(run.created_at).toLocaleString('it-IT') : '—'}
            </p>
          </div>
          <div>
            <span className="text-slate-500">Fixture / strategie</span>
            <p className="font-medium text-slate-900">
              {String(summary.fixtures_count ?? '—')} / {String(summary.strategies_count ?? '—')}
            </p>
          </div>
          <div>
            <span className="text-slate-500">Strategia consigliata</span>
            <p className="font-medium text-slate-900">{String(summary.recommended_strategy ?? '—')}</p>
          </div>
          {summary.main_warning ? (
            <div className="sm:col-span-2 lg:col-span-4">
              <span className="text-slate-500">Warning</span>
              <p className="font-medium text-amber-900">{String(summary.main_warning)}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
