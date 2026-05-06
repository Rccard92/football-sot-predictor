import type { AuditResponse, AuditSection } from './types'

function jsonPreview(x: unknown): string {
  try {
    return JSON.stringify(x, null, 2)
  } catch {
    return String(x)
  }
}

export function TechnicalAuditPanel({ data }: { data: AuditResponse }) {
  const fx = data.fixture
  const nonUsateBySection = data.sections
    .map((s) => ({
      ...s,
      variables: s.variables.filter((v) => !v.display_in_main_audit),
    }))
    .filter((s) => s.variables.length > 0)

  return (
    <section className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm">
      <details className="rounded-2xl border border-slate-200 bg-slate-50/30">
        <summary className="cursor-pointer select-none px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-slate-900">Audit completo / dati disponibili non usati</p>
              <p className="mt-1 text-xs text-slate-600">
                Variabili disponibili ma non applicate, debug, roadmap, supporto tecnico (chiuso di default).
              </p>
            </div>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
              Completo
            </span>
          </div>
        </summary>

        <div className="border-t border-slate-200 p-4 space-y-3">
          {nonUsateBySection.map((s) => (
            <details key={s.id} className="rounded-2xl border border-slate-200 bg-white">
              <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-slate-800">
                {s.title} <span className="text-xs text-slate-500">({s.variables.length})</span>
              </summary>
              <div className="border-t border-slate-200 p-3">
                <div className="grid gap-2 md:grid-cols-2">
                  {s.variables.map((v) => (
                    <div key={`${s.id}-${v.key}-${v.team_id ?? 'na'}`} className="rounded-2xl border border-slate-200 bg-slate-50/40 p-3">
                      <p className="text-xs font-semibold text-slate-900">{v.label}</p>
                      <p className="mt-1 text-[11px] text-slate-600">
                        {v.team_name ? `${v.team_name} · ` : ''}
                        {v.key}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </details>
          ))}
        </div>
      </details>

      <details className="rounded-2xl border border-slate-200 bg-slate-50/30">
        <summary className="cursor-pointer select-none px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-slate-900">Debug raw (JSON)</p>
              <p className="mt-1 text-xs text-slate-600">
                Dettagli raw e payload completo (chiuso di default).
              </p>
            </div>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
              Debug
            </span>
          </div>
        </summary>

        <div className="border-t border-slate-200 p-4 space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Identificativi</p>
              <p className="mt-2 text-sm text-slate-800">
                fixture_id: <strong>{fx.fixture_id}</strong>
              </p>
              <p className="mt-1 text-sm text-slate-800">
                api_fixture_id: <strong>{fx.api_fixture_id}</strong>
              </p>
              <p className="mt-1 text-sm text-slate-800">
                status_short: <strong>{fx.status_short}</strong>
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Policy</p>
              <pre className="mt-2 overflow-x-auto rounded-2xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-800">
                {jsonPreview(data.data_policy)}
              </pre>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Sezioni (raw)</p>
            <div className="mt-2 space-y-3">
              {data.sections.map((s: AuditSection) => (
                <details key={s.id} className="rounded-2xl border border-slate-200 bg-slate-50/40">
                  <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-slate-800">
                    {s.title} <span className="text-xs text-slate-500">({s.variables.length} variabili)</span>
                  </summary>
                  <div className="border-t border-slate-200 p-3">
                    <pre className="overflow-x-auto rounded-2xl border border-slate-200 bg-white p-3 text-xs text-slate-800">
                      {jsonPreview(s)}
                    </pre>
                  </div>
                </details>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Payload completo</p>
            <pre className="mt-2 overflow-x-auto rounded-2xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-800">
              {jsonPreview(data)}
            </pre>
          </div>
        </div>
      </details>
    </section>
  )
}

