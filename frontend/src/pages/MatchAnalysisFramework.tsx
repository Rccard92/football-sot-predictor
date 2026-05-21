import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getMatchAnalysisFramework,
  type FrameworkImplementationStatus,
  type FrameworkMarketId,
  type MatchAnalysisFrameworkArea,
  type MatchAnalysisFrameworkResponse,
  type MatchAnalysisFrameworkVariable,
} from '../lib/api'

type RoadmapStatus =
  | 'Applicata al modello'
  | 'Disponibile, non usata'
  | 'Da implementare'
  | 'Non disponibile nel provider attuale'

function roadmapStatusFor(v: MatchAnalysisFrameworkVariable): RoadmapStatus {
  if (v.applied_now) return 'Applicata al modello'
  if (v.implementation_status === 'da implementare') return 'Da implementare'
  if (v.implementation_status === 'non disponibile') return 'Non disponibile nel provider attuale'
  return 'Disponibile, non usata'
}

function roadmapBadgeClass(s: RoadmapStatus): string {
  if (s === 'Applicata al modello') return 'bg-emerald-50 text-emerald-900 ring-emerald-200'
  if (s === 'Da implementare') return 'bg-amber-100 text-amber-950 ring-amber-200'
  if (s === 'Non disponibile nel provider attuale') return 'bg-slate-100 text-slate-700 ring-slate-200'
  return 'bg-slate-100 text-slate-700 ring-slate-200'
}

function weightBadgeClass(weight: number): string {
  if (weight >= 90) return 'bg-rose-100 text-rose-900 ring-rose-200'
  if (weight >= 70) return 'bg-orange-100 text-orange-900 ring-orange-200'
  if (weight >= 40) return 'bg-indigo-100 text-indigo-900 ring-indigo-200'
  if (weight >= 10) return 'bg-slate-100 text-slate-900 ring-slate-200'
  return 'bg-slate-200 text-slate-700 ring-slate-300'
}

function marketLabel(m: FrameworkMarketId): string {
  if (m === 'tiri_in_porta') return 'Tiri in porta'
  if (m === 'tiri_totali') return 'Tiri totali'
  if (m === 'corner') return "Calci d’angolo"
  if (m === 'cartellini') return 'Cartellini'
  if (m === 'falli') return 'Falli'
  return 'Goal / Over Under'
}

function uniq<T>(arr: T[]): T[] {
  return Array.from(new Set(arr))
}

export function MatchAnalysisFramework() {
  const [data, setData] = useState<MatchAnalysisFrameworkResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [q, setQ] = useState('')
  const [areaId, setAreaId] = useState<string>('all')
  const [marketId, setMarketId] = useState<FrameworkMarketId | 'all'>('all')
  const [status, setStatus] = useState<FrameworkImplementationStatus | 'all'>('all')
  const [appliedNow, setAppliedNow] = useState<'all' | 'yes' | 'no'>('all')

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        setData(await getMatchAnalysisFramework())
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [])

  const allAreas: MatchAnalysisFrameworkArea[] = data?.areas ?? []
  const allVariables: MatchAnalysisFrameworkVariable[] = useMemo(
    () => allAreas.flatMap((a) => a.variables.map((v) => ({ ...v, area: v.area || a.title }))),
    [allAreas],
  )

  const availableAreaOptions = useMemo(
    () => [{ id: 'all', title: 'Tutte le aree' }, ...allAreas.map((a) => ({ id: a.id, title: a.title }))],
    [allAreas],
  )

  const filteredAreas = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const matchesVar = (v: MatchAnalysisFrameworkVariable) => {
      if (marketId !== 'all' && !v.impacted_markets.includes(marketId)) return false
      if (status !== 'all' && v.implementation_status !== status) return false
      if (appliedNow !== 'all' && v.applied_now !== (appliedNow === 'yes')) return false
      if (!needle) return true
      const hay = `${v.name} ${v.key} ${v.description} ${v.area} ${v.data_source} ${v.notes ?? ''}`.toLowerCase()
      return hay.includes(needle)
    }

    return allAreas
      .filter((a) => (areaId === 'all' ? true : a.id === areaId))
      .map((a) => ({ ...a, variables: a.variables.filter(matchesVar) }))
      .filter((a) => a.variables.length > 0)
  }, [allAreas, q, areaId, marketId, status, appliedNow])

  const counts = useMemo(() => {
    const vars = allVariables
    return {
      variablesTotal: vars.length,
      variablesApplied: vars.filter((v) => v.applied_now).length,
      areasTotal: allAreas.length,
      areasShown: filteredAreas.length,
    }
  }, [allAreas.length, allVariables, filteredAreas.length])

  const marketsAvailable = useMemo(() => {
    const all = uniq(allVariables.flatMap((v) => v.impacted_markets))
    const ordered: FrameworkMarketId[] = [
      'tiri_in_porta',
      'tiri_totali',
      'corner',
      'cartellini',
      'falli',
      'goal_over_under',
    ]
    return ordered.filter((m) => all.includes(m))
  }, [allVariables])

  return (
    <div className="space-y-6 pb-8">
        <header className="pt-4 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Framework Analisi Partita</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-600">
                Roadmap completa delle variabili. Questa pagina <strong>non</strong> serve per decidere la previsione del singolo match.
              </p>
            </div>
            <div className="text-xs text-slate-600">
              <Link to="/model-legend" className="font-medium text-slate-700 underline">
                Torna alla Legenda Modello
              </Link>
            </div>
          </div>
        </header>

        <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-700">
            Il modello non guarda una singola statistica: compila una “scheda partita”, valuta la qualità del dato,
            calcola una stima base, applica correzioni (giocatori/contesto) e infine decide se la giocata è
            <strong> giocabile</strong>, <strong>prudente</strong> o <strong>no bet</strong>.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-4">
            <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-3 text-xs text-slate-700">
              <p className="font-semibold text-slate-900">{counts.areasTotal}</p>
              <p>Aree</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-3 text-xs text-slate-700">
              <p className="font-semibold text-slate-900">{counts.variablesTotal}</p>
              <p>Variabili</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-3 text-xs text-slate-700">
              <p className="font-semibold text-slate-900">{counts.variablesApplied}</p>
              <p>Applicate ora</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-3 text-xs text-slate-700">
              <p className="font-semibold text-slate-900">{counts.areasShown}</p>
              <p>Aree in vista (filtri)</p>
            </div>
          </div>
        </section>

        {loading ? (
          <div className="space-y-3">
            <div className="h-24 animate-pulse rounded-2xl bg-slate-200/80" />
            <div className="h-48 animate-pulse rounded-2xl bg-slate-200/80" />
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
            {error}
          </div>
        ) : data ? (
          <>
            <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
              <div className="grid gap-3 sm:grid-cols-5">
                <div className="sm:col-span-2">
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-600">Cerca variabile</label>
                  <input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="es. tiri in porta, turnover, arbitro…"
                    className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-600">Area</label>
                  <select
                    value={areaId}
                    onChange={(e) => setAreaId(e.target.value)}
                    className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
                  >
                    {availableAreaOptions.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.title}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-600">Mercato</label>
                  <select
                    value={marketId}
                    onChange={(e) => setMarketId(e.target.value as FrameworkMarketId | 'all')}
                    className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
                  >
                    <option value="all">Tutti</option>
                    {marketsAvailable.map((m) => (
                      <option key={m} value={m}>
                        {marketLabel(m)}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-600">Stato</label>
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value as FrameworkImplementationStatus | 'all')}
                    className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
                  >
                    <option value="all">Tutti</option>
                    <option value="implementata">Implementata</option>
                    <option value="parzialmente implementata">Parzialmente implementata</option>
                    <option value="solo debug">Solo debug</option>
                    <option value="da implementare">Da implementare</option>
                  </select>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-600">Applicata ora</label>
                  <div className="mt-2 inline-flex rounded-2xl border border-slate-200 bg-white p-1 text-xs shadow-sm">
                    {(['all', 'yes', 'no'] as const).map((x) => (
                      <button
                        key={x}
                        type="button"
                        className={`rounded-xl px-3 py-1.5 ${
                          appliedNow === x ? 'bg-slate-900 text-white' : 'text-slate-700'
                        }`}
                        onClick={() => setAppliedNow(x)}
                      >
                        {x === 'all' ? 'Tutte' : x === 'yes' ? 'Sì' : 'No'}
                      </button>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-slate-600">
                  Endpoint: <code className="rounded bg-slate-100 px-1">/api/model/match-analysis-framework</code> ·
                  Versione: <span className="font-medium text-slate-800">{data.version}</span>
                </p>
              </div>
            </section>

            <section className="space-y-3">
              {filteredAreas.map((area) => (
                <details
                  key={area.id}
                  className="group overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm"
                  open
                >
                  <summary className="cursor-pointer list-none px-5 py-4 marker:hidden [&::-webkit-details-marker]:hidden">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{area.title}</p>
                        <p className="mt-1 text-xs text-slate-600">{area.description}</p>
                      </div>
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
                        {area.variables.length} variabili
                      </span>
                    </div>
                  </summary>

                  <div className="border-t border-slate-100 p-5">
                    <div className="grid gap-3 sm:grid-cols-2">
                      {area.variables.map((v) => (
                        <article
                          key={`${area.id}-${v.key}`}
                          className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <p className="text-sm font-semibold text-slate-900">{v.name}</p>
                              <p className="mt-1 text-xs text-slate-500">{v.key}</p>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              <span
                                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${roadmapBadgeClass(
                                  roadmapStatusFor(v),
                                )}`}
                              >
                                {roadmapStatusFor(v)}
                              </span>
                              <span
                                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${weightBadgeClass(
                                  v.theoretical_weight,
                                )}`}
                              >
                                Peso {v.theoretical_weight}/100
                              </span>
                              {v.implementation_status === 'solo debug' ? (
                                <span className="rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-800 ring-1 ring-slate-300">
                                  Solo debug
                                </span>
                              ) : null}
                            </div>
                          </div>

                          <p className="mt-3 text-sm text-slate-700">{v.description}</p>

                          <div className="mt-3 grid gap-2 text-xs text-slate-700 sm:grid-cols-2">
                            <div className="rounded-xl border border-slate-200 bg-white p-2.5">
                              <p className="font-semibold text-slate-900">Mercati impattati</p>
                              <p className="mt-1 text-slate-700">
                                {v.impacted_markets.map(marketLabel).join(' · ')}
                              </p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white p-2.5">
                              <p className="font-semibold text-slate-900">Fonte dati possibile</p>
                              <p className="mt-1 text-slate-700">{v.data_source}</p>
                            </div>
                          </div>

                          {v.notes ? (
                            <p className="mt-3 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700">
                              <span className="font-semibold text-slate-900">Note:</span> {v.notes}
                            </p>
                          ) : null}

                          {v.application_role ? (
                            <div className="mt-3 rounded-xl border border-slate-200 bg-white p-2.5 text-xs text-slate-700">
                              <p>
                                <span className="font-semibold text-slate-900">Ruolo nel modello:</span> {v.application_role}
                              </p>
                              {v.parent_component ? (
                                <p className="mt-1">
                                  <span className="font-semibold text-slate-900">Componente padre:</span>{' '}
                                  <span className="font-mono">{v.parent_component}</span>
                                </p>
                              ) : null}
                              {v.applied_to_model_versions?.length ? (
                                <p className="mt-1">
                                  <span className="font-semibold text-slate-900">Model version:</span>{' '}
                                  <span className="font-mono">{v.applied_to_model_versions.join(', ')}</span>
                                </p>
                              ) : null}
                              {v.expected_in_debug != null ? (
                                <p className="mt-1">
                                  <span className="font-semibold text-slate-900">Attesa in debug:</span>{' '}
                                  {v.expected_in_debug ? 'sì' : 'no'}
                                </p>
                              ) : null}
                            </div>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  </div>
                </details>
              ))}
            </section>

            <section className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-slate-900">Framework per mercato</h2>
              <p className="mt-2 text-sm text-slate-600">
                Ogni mercato valorizza variabili diverse: principali, secondarie, warning e meno rilevanti.
              </p>

              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {data.market_frameworks.map((mf) => (
                  <article key={mf.id} className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4">
                    <p className="text-sm font-semibold text-slate-900">{mf.title}</p>
                    <p className="mt-1 text-xs text-slate-500">{marketLabel(mf.id)}</p>

                    {(
                      [
                        ['Variabili principali', mf.primary_variables],
                        ['Variabili secondarie', mf.secondary_variables],
                        ['Variabili warning', mf.warning_variables],
                        ['Meno rilevanti', mf.less_relevant_variables],
                      ] as const
                    ).map(([label, list]) => (
                      <div key={label} className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">{label}</p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {list.length ? (
                            list.map((k) => (
                              <span
                                key={`${mf.id}-${label}-${k}`}
                                className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700 ring-1 ring-slate-200"
                              >
                                {k}
                              </span>
                            ))
                          ) : (
                            <span className="text-xs text-slate-500">—</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </article>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-indigo-200 bg-indigo-50/60 p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-indigo-950">Pesi modificabili da frontend</h2>
              <p className="mt-2 text-sm text-indigo-950">
                In questa versione i pesi sono statici e documentali. In una prossima fase sarà possibile modificarli
                dall’interfaccia, salvarli come configurazione modello e ricalcolare le previsioni.
              </p>
              <p className="mt-3 text-xs text-indigo-900">
                Stato attuale: <strong>{data.future_editable_weights.enabled_now ? 'abilitato' : 'non abilitato'}</strong>{' '}
                · Pianificato: <strong>{data.future_editable_weights.planned ? 'sì' : 'no'}</strong>
              </p>
            </section>
          </>
        ) : null}
    </div>
  )
}

