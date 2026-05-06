import type { AuditResponse, AuditVariable } from './types'
import { AuditVariableCard } from './AuditVariableCard'
 
function uniqueByKeyTeam(xs: AuditVariable[]): AuditVariable[] {
  const out: AuditVariable[] = []
  const seen = new Set<string>()
  for (const x of xs) {
    const k = `${x.key}:${x.team_id ?? 'na'}`
    if (seen.has(k)) continue
    seen.add(k)
    out.push(x)
  }
  return out
}

export function FrameworkLevelSection({ data }: { data: AuditResponse }) {
  const mainVars = uniqueByKeyTeam(
    data.sections
      .flatMap((s) => s.variables)
      .filter(
        (v) =>
          v.applied_to_active_model === true &&
          v.is_supporting_variable !== true &&
          v.display_in_main_audit !== false,
      ),
  )

  return (
    <section className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Componenti applicate al calcolo</h2>
      <p className="mt-2 text-sm text-slate-600">
        Vista principale: mostra solo ciò che impatta il <strong>modello attivo</strong>. Tutto il resto è nel pannello
        “Audit completo / dati disponibili non usati”.
      </p>

      {mainVars.length ? (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {mainVars.map((v) => (
            <AuditVariableCard key={`${v.key}:${v.team_id ?? 'na'}`} v={v} />
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-600">Nessuna variabile marcata come applicata al modello attivo.</p>
      )}
    </section>
  )
}

