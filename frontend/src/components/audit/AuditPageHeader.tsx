import { Link } from 'react-router-dom'
import type { AuditMode, FixturesListItem } from './types'

export function AuditPageHeader({
  fixtures,
  fixtureId,
  onFixtureChange,
  mode,
  onModeChange,
  activeModelVersion,
}: {
  fixtures: FixturesListItem[]
  fixtureId: number | null
  onFixtureChange: (fixtureId: number) => void
  mode: AuditMode
  onModeChange: (mode: AuditMode) => void
  activeModelVersion: string | null
}) {
  return (
    <header className="pt-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Audit Variabili</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Controllo centrale: mostra <strong>solo</strong> ciò che è <strong>applicato al calcolo</strong> del modello attivo.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
          <Link to="/" className="font-medium text-slate-700 underline">
            Torna a Prossima giornata
          </Link>
          <span className="text-slate-300">|</span>
          <Link to="/match-analysis-framework" className="font-medium text-slate-700 underline">
            Framework Analisi (roadmap)
          </Link>
        </div>
      </div>

      <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-600">Partita</label>
            <select
              value={fixtureId ?? ''}
              onChange={(e) => onFixtureChange(Number(e.target.value))}
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
            >
              {fixtures.map((f) => (
                <option key={f.fixture_id} value={f.fixture_id}>
                  {f.round ?? 'Giornata'} · {f.home_team.name} vs {f.away_team.name} ·{' '}
                  {new Date(f.kickoff_at).toLocaleString('it-IT')}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-600">Modalità</label>
            <select
              value={mode}
              onChange={(e) => onModeChange(e.target.value as AuditMode)}
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
            >
              <option value="pre_match">Pre-match</option>
              <option value="post_match">Post-match audit</option>
            </select>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-600">
            Mercato: <span className="font-medium text-slate-800">Tiri in porta</span>
          </p>
          <p className="text-xs text-slate-600">
            Modello attivo:{' '}
            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 font-medium text-slate-800 ring-1 ring-slate-200">
              {activeModelVersion ?? '—'}
            </span>
          </p>
          <p className="text-xs text-slate-600">
            {mode === 'pre_match' ? (
              <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 font-medium text-emerald-900 ring-1 ring-emerald-200">
                No data leakage
              </span>
            ) : (
              <span className="rounded-full bg-amber-50 px-2.5 py-0.5 font-medium text-amber-900 ring-1 ring-amber-200">
                Audit post-match
              </span>
            )}
          </p>
        </div>
      </section>
    </header>
  )
}

