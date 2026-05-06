import type { AuditResponse, AuditVariable } from './types'
import { AuditVariableCard } from './AuditVariableCard'
import { coreKeys, idxVars, pickTeamVar, playerKeys } from './mapping'

type LevelDef = {
  id: string
  title: string
  description: string
  kind: 'cards' | 'roadmap'
}

const levels: LevelDef[] = [
  {
    id: 'core',
    title: 'Livello 1 — Core statistico',
    description: 'Medie stagione, forma recente, split casa/trasferta e concessi (auditabili).',
    kind: 'cards',
  },
  {
    id: 'player',
    title: 'Livello 2 — Player layer',
    description: 'Top player e correzione player impact (v0.2).',
    kind: 'cards',
  },
  {
    id: 'tactical',
    title: 'Livello 3 — Tattica / contesto',
    description: 'Roadmap: matchup, ritmo, stile di gioco (non auditato in questo step).',
    kind: 'roadmap',
  },
  {
    id: 'motivation',
    title: 'Livello 4 — Motivazione / classifica',
    description: 'Roadmap: contesto fine stagione, obiettivi, derby (warning).',
    kind: 'roadmap',
  },
  {
    id: 'market',
    title: 'Livello 5 — Mercato quote',
    description: 'Roadmap: line movement/odds (non incluso in questo step).',
    kind: 'roadmap',
  },
  {
    id: 'referee',
    title: 'Livello 6 — Arbitro',
    description: 'Roadmap: falli/cartellini/rigori (non auditato in questo step).',
    kind: 'roadmap',
  },
  {
    id: 'sentiment',
    title: 'Livello 7 — Sentiment / news',
    description: 'Roadmap: layer qualitativo (warning), non automatizzato.',
    kind: 'roadmap',
  },
]

function collectKeysForLevel(levelId: string): string[] {
  if (levelId === 'core') return [...coreKeys]
  if (levelId === 'player') return [...playerKeys]
  return []
}

function uniqueByKeyTeam(xs: (AuditVariable | null)[]): AuditVariable[] {
  const out: AuditVariable[] = []
  const seen = new Set<string>()
  for (const x of xs) {
    if (!x) continue
    const k = `${x.key}:${x.team_id ?? 'na'}`
    if (seen.has(k)) continue
    seen.add(k)
    out.push(x)
  }
  return out
}

export function FrameworkLevelSection({ data }: { data: AuditResponse }) {
  const fx = data.fixture
  const idx = idxVars(data)

  return (
    <section className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Framework per livelli</h2>
      <p className="mt-2 text-sm text-slate-600">
        Variabili organizzate secondo il framework. I layer non auditati sono mostrati come roadmap compatta.
      </p>

      <div className="mt-4 space-y-3">
        {levels.map((lvl) => {
          const keys = collectKeysForLevel(lvl.id)
          const vars =
            lvl.kind === 'cards'
              ? uniqueByKeyTeam([
                  ...keys.map((k) => pickTeamVar(idx, k, fx.home_team.id)),
                  ...keys.map((k) => pickTeamVar(idx, k, fx.away_team.id)),
                  // variabili non team-based (se presenti) le prendiamo dalla prima occorrenza
                  ...keys.map((k) => (idx[k]?.find((v) => v.team_id == null) ?? null)),
                ])
              : []

          return (
            <details key={lvl.id} className="rounded-2xl border border-slate-200 bg-slate-50/30">
              <summary className="cursor-pointer select-none px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{lvl.title}</p>
                    <p className="mt-1 text-xs text-slate-600">{lvl.description}</p>
                  </div>
                  <p className="text-xs text-slate-500">
                    {lvl.kind === 'cards' ? `${vars.length} variabili` : 'Roadmap'}
                  </p>
                </div>
              </summary>

              <div className="border-t border-slate-200 p-4">
                {lvl.kind === 'cards' ? (
                  vars.length ? (
                    <div className="grid gap-3 lg:grid-cols-2">
                      {vars.map((v) => (
                        <AuditVariableCard key={`${v.key}:${v.team_id ?? 'na'}`} v={v} />
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-600">Nessuna variabile trovata per questo livello.</p>
                  )
                ) : (
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-sm text-slate-700">
                      Questo livello è mostrato come <strong>roadmap</strong> finché non diventa auditabile.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs">
                      {[
                        'matchup tattico',
                        'ritmo partita',
                        'motivazione/classifica',
                        'quote e movimento linea',
                        'arbitro',
                        'sentiment/news',
                      ].map((x) => (
                        <span
                          key={x}
                          className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700 ring-1 ring-slate-200"
                        >
                          {x}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </details>
          )
        })}
      </div>
    </section>
  )
}

