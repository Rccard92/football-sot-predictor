import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

type AuditMode = 'pre_match' | 'post_match'

type AuditTeamBlock = { id: number; name: string; logo_url?: string | null }
type AuditFixtureBlock = {
  fixture_id: number
  api_fixture_id: number
  round: string | null
  kickoff_at: string
  status_short: string
  home_team: AuditTeamBlock
  away_team: AuditTeamBlock
}

type AuditSampleRow = {
  fixture_id: number
  date: string
  home_team: string
  away_team: string
  team: string
  team_id: number
  opponent: string
  opponent_id: number
  side: 'home' | 'away'
  shots_on_target: number | null
  total_shots: number | null
  goals_for: number | null
  goals_against: number | null
}

type AuditVariable = {
  key: string
  label: string
  team_id: number | null
  team_name: string | null
  value: number | null
  unit: string | null
  status: 'available' | 'missing' | 'partial' | 'not_applicable'
  implementation_status: 'implemented' | 'partial' | 'debug_only' | 'todo'
  applied_to_model: boolean
  weight: number | null
  weight_label: string | null
  source_table: string | null
  source_description: string | null
  calculation: { formula: string; meta?: Record<string, unknown> | null; result?: number | null } | null
  sample_rows: AuditSampleRow[]
  notes: string | null
}

type AuditSection = {
  id: string
  title: string
  variables: AuditVariable[]
  variables_available: number
  variables_missing: number
  completeness_pct: number
}

type AuditResponse = {
  fixture: AuditFixtureBlock
  market: 'shots_on_target'
  mode: AuditMode
  data_policy: { no_data_leakage: boolean; included_matches_rule: string }
  sections: AuditSection[]
  model_inputs_summary: {
    home_team_expected_sot_v01: number | null
    away_team_expected_sot_v01: number | null
    home_team_expected_sot_v02: number | null
    away_team_expected_sot_v02: number | null
  }
}

type FixturesListItem = {
  fixture_id: number
  api_fixture_id: number
  round: string | null
  kickoff_at: string
  status_short: string
  home_team: AuditTeamBlock
  away_team: AuditTeamBlock
}

type FixturesListResponse = {
  season: number | null
  scope: 'upcoming' | 'completed' | 'all'
  fixtures: FixturesListItem[]
}

function useQuery(): URLSearchParams {
  const { search } = useLocation()
  return useMemo(() => new URLSearchParams(search), [search])
}

function badgeClassStatus(s: AuditVariable['status']): string {
  if (s === 'available') return 'bg-emerald-100 text-emerald-900 ring-emerald-200'
  if (s === 'partial') return 'bg-blue-100 text-blue-900 ring-blue-200'
  if (s === 'missing') return 'bg-rose-100 text-rose-900 ring-rose-200'
  return 'bg-slate-200 text-slate-800 ring-slate-300'
}

export function MatchVariableAudit() {
  const qs = useQuery()
  const fixtureIdFromQS = Number(qs.get('fixture_id') || '')

  const [fixtures, setFixtures] = useState<FixturesListItem[]>([])
  const [fixtureId, setFixtureId] = useState<number | null>(
    Number.isFinite(fixtureIdFromQS) && fixtureIdFromQS > 0 ? fixtureIdFromQS : null,
  )
  const [mode, setMode] = useState<AuditMode>('pre_match')
  const market = 'shots_on_target' as const

  const [loadingList, setLoadingList] = useState(true)
  const [loadingAudit, setLoadingAudit] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<AuditResponse | null>(null)

  useEffect(() => {
    const loadFixtures = async () => {
      setLoadingList(true)
      setError(null)
      try {
        const res = (await fetch(
          `${import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')}/api/match-analysis/fixtures?scope=upcoming&limit=60`,
        ).then((r) => r.json())) as FixturesListResponse
        setFixtures(res.fixtures ?? [])
        if (fixtureId == null && res.fixtures?.length) {
          setFixtureId(res.fixtures[0].fixture_id)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoadingList(false)
      }
    }
    void loadFixtures()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const loadAudit = async () => {
      if (!fixtureId) return
      setLoadingAudit(true)
      setError(null)
      try {
        const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')
        const url = `${base}/api/match-analysis/fixture/${fixtureId}/variables?market=${market}&mode=${mode}`
        const res = await fetch(url)
        const parsed = (await res.json()) as unknown
        if (!res.ok) {
          const o = parsed as Record<string, unknown>
          throw new Error((o.message as string) || (o.detail as string) || 'Richiesta non riuscita')
        }
        setData(parsed as AuditResponse)
      } catch (e) {
        setData(null)
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoadingAudit(false)
      }
    }
    void loadAudit()
  }, [fixtureId, mode])

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-6xl space-y-6 px-4 sm:px-6">
        <header className="pt-4 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Audit Variabili Partita</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-600">
                Controlla come il modello riempie le variabili prima di generare la previsione.
              </p>
            </div>
            <div className="text-xs text-slate-600">
              <Link to="/" className="font-medium text-slate-700 underline">
                Torna a Prossima giornata
              </Link>
            </div>
          </div>
        </header>

        <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="sm:col-span-2">
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-600">Partita</label>
              <select
                disabled={loadingList}
                value={fixtureId ?? ''}
                onChange={(e) => setFixtureId(Number(e.target.value))}
                className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
              >
                {fixtures.map((f) => (
                  <option key={f.fixture_id} value={f.fixture_id}>
                    {f.round ?? 'Giornata'} · {f.home_team.name} vs {f.away_team.name} · {new Date(f.kickoff_at).toLocaleString('it-IT')}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-600">Modalità</label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as AuditMode)}
                className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
              >
                <option value="pre_match">Pre-match (no leakage)</option>
                <option value="post_match">Post-match audit</option>
              </select>
            </div>
          </div>

          <div className="mt-4 rounded-2xl border border-indigo-200 bg-indigo-50/60 p-4 text-sm text-indigo-950">
            <p className="font-semibold">Policy dati</p>
            <p className="mt-1 text-sm">
              In <strong>pre-match</strong> usiamo solo fixture concluse con kickoff precedente alla fixture analizzata.
              In <strong>post-match</strong> è consentito includere dati successivi solo a scopo audit.
            </p>
          </div>
        </section>

        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
            {error}
          </div>
        ) : null}

        {loadingAudit ? (
          <div className="space-y-3">
            <div className="h-24 animate-pulse rounded-2xl bg-slate-200/80" />
            <div className="h-48 animate-pulse rounded-2xl bg-slate-200/80" />
          </div>
        ) : data ? (
          <>
            <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Fixture</p>
              <p className="mt-1 text-lg font-semibold text-slate-900">
                {data.fixture.home_team.name} vs {data.fixture.away_team.name}
              </p>
              <p className="mt-1 text-sm text-slate-600">
                {data.fixture.round ?? 'Giornata'} · {new Date(data.fixture.kickoff_at).toLocaleString('it-IT')} · Mode:{' '}
                <span className="font-medium text-slate-800">{data.mode}</span>
              </p>
              <p className="mt-2 text-xs text-slate-600">
                <strong>No leakage:</strong> {data.data_policy.no_data_leakage ? 'Sì' : 'No'} ·{' '}
                {data.data_policy.included_matches_rule}
              </p>
            </section>

            <section className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Input modello (v0.1)</p>
                <p className="mt-2 text-sm text-slate-700">
                  Home expected: <strong>{data.model_inputs_summary.home_team_expected_sot_v01 ?? '—'}</strong>
                </p>
                <p className="text-sm text-slate-700">
                  Away expected: <strong>{data.model_inputs_summary.away_team_expected_sot_v01 ?? '—'}</strong>
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Input modello (v0.2 PA)</p>
                <p className="mt-2 text-sm text-slate-700">
                  Home expected: <strong>{data.model_inputs_summary.home_team_expected_sot_v02 ?? '—'}</strong>
                </p>
                <p className="text-sm text-slate-700">
                  Away expected: <strong>{data.model_inputs_summary.away_team_expected_sot_v02 ?? '—'}</strong>
                </p>
              </div>
            </section>

            <section className="space-y-3">
              {data.sections.map((s) => (
                <details
                  key={s.id}
                  className="group overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm"
                  open
                >
                  <summary className="cursor-pointer list-none px-5 py-4 marker:hidden [&::-webkit-details-marker]:hidden">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{s.title}</p>
                        <p className="mt-1 text-xs text-slate-600">
                          Completezza: <strong>{s.completeness_pct}%</strong> · disponibili {s.variables_available} ·
                          mancanti {s.variables_missing}
                        </p>
                      </div>
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
                        {s.variables.length} variabili
                      </span>
                    </div>
                  </summary>

                  <div className="border-t border-slate-100 p-5">
                    <div className="grid gap-3 sm:grid-cols-2">
                      {s.variables.map((v) => (
                        <article key={`${s.id}-${v.key}-${v.team_id ?? 'na'}`} className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <p className="text-sm font-semibold text-slate-900">{v.label}</p>
                              <p className="mt-1 text-xs text-slate-500">
                                {v.key}
                                {v.team_name ? ` · ${v.team_name}` : ''}
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${badgeClassStatus(v.status)}`}>
                                {v.status}
                              </span>
                              <span
                                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${
                                  v.applied_to_model ? 'bg-emerald-50 text-emerald-900 ring-emerald-200' : 'bg-slate-100 text-slate-700 ring-slate-200'
                                }`}
                              >
                                {v.applied_to_model ? 'Applicata al modello' : 'Non applicata'}
                              </span>
                            </div>
                          </div>

                          <p className="mt-3 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
                            {v.value ?? '—'} {v.unit ?? ''}
                          </p>

                          <div className="mt-3 grid gap-2 text-xs text-slate-700 sm:grid-cols-2">
                            <div className="rounded-xl border border-slate-200 bg-white p-2.5">
                              <p className="font-semibold text-slate-900">Peso</p>
                              <p className="mt-1">{v.weight_label ?? (v.weight != null ? String(v.weight) : '—')}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white p-2.5">
                              <p className="font-semibold text-slate-900">Fonte</p>
                              <p className="mt-1">{v.source_table ?? '—'}</p>
                              <p className="mt-1 text-slate-600">{v.source_description ?? ''}</p>
                            </div>
                          </div>

                          {v.calculation ? (
                            <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-700">
                              <p className="font-semibold text-slate-900">Formula</p>
                              <p className="mt-1">{v.calculation.formula}</p>
                              {v.calculation.meta ? (
                                <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-2 text-[11px] text-slate-700">
{JSON.stringify(v.calculation.meta, null, 2)}
                                </pre>
                              ) : null}
                            </div>
                          ) : null}

                          {v.notes ? (
                            <p className="mt-3 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700">
                              <span className="font-semibold text-slate-900">Note:</span> {v.notes}
                            </p>
                          ) : null}

                          {v.sample_rows?.length ? (
                            <details className="mt-3 rounded-xl border border-slate-200 bg-white">
                              <summary className="cursor-pointer list-none px-3 py-2 text-xs font-semibold text-slate-800 marker:hidden [&::-webkit-details-marker]:hidden">
                                Vedi esempio partite considerate (ultime {v.sample_rows.length})
                              </summary>
                              <div className="border-t border-slate-200 p-3">
                                <p className="mb-3 text-xs text-slate-600">
                                  Il calcolo usa tutte le partite valide: <strong>{String((v.calculation?.meta as any)?.matches_count ?? '—')}</strong>. Qui ne vengono mostrate solo {v.sample_rows.length} per comodità.
                                </p>
                                <div className="overflow-x-auto">
                                  <table className="min-w-full text-left text-xs">
                                    <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-600">
                                      <tr>
                                        <th className="px-2 py-2">Data</th>
                                        <th className="px-2 py-2">Partita</th>
                                        <th className="px-2 py-2">Lato</th>
                                        <th className="px-2 py-2">SOT</th>
                                        <th className="px-2 py-2">Tiri</th>
                                        <th className="px-2 py-2">GF</th>
                                        <th className="px-2 py-2">GA</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                      {v.sample_rows.map((r) => (
                                        <tr key={`${v.key}-${r.fixture_id}-${r.team_id}`}>
                                          <td className="px-2 py-2 whitespace-nowrap">
                                            {new Date(r.date).toLocaleDateString('it-IT')}
                                          </td>
                                          <td className="px-2 py-2 whitespace-nowrap">
                                            {r.home_team} vs {r.away_team}
                                          </td>
                                          <td className="px-2 py-2">{r.side}</td>
                                          <td className="px-2 py-2">{r.shots_on_target ?? '—'}</td>
                                          <td className="px-2 py-2">{r.total_shots ?? '—'}</td>
                                          <td className="px-2 py-2">{r.goals_for ?? '—'}</td>
                                          <td className="px-2 py-2">{r.goals_against ?? '—'}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            </details>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  </div>
                </details>
              ))}
            </section>
          </>
        ) : null}
      </div>
    </div>
  )
}

