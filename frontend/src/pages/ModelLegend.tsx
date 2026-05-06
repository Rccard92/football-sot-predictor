import { useEffect, useMemo, useState } from 'react'

import { getModelLegend, type ModelLegendResponse, type ModelLegendStatus } from '../lib/api'

function statusBadgeClass(status: ModelLegendStatus): string {
  if (status === 'applicata') return 'bg-emerald-100 text-emerald-800'
  if (status === 'solo_debug') return 'bg-slate-200 text-slate-700'
  if (status === 'applicata_alla_lettura') return 'bg-blue-100 text-blue-800'
  return 'bg-amber-100 text-amber-800'
}

function statusLabel(status: ModelLegendStatus): string {
  if (status === 'applicata') return 'Applicata'
  if (status === 'solo_debug') return 'Solo debug'
  if (status === 'applicata_alla_lettura') return 'Applicata alla lettura'
  return 'Non applicata'
}

export function ModelLegend() {
  const [data, setData] = useState<ModelLegendResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        setData(await getModelLegend())
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [])

  const baseline = useMemo(
    () => data?.sections.find((s) => s.id === 'baseline_formula') ?? null,
    [data],
  )

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-6xl space-y-6 px-4 sm:px-6">
        <header className="pt-4">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Legenda Modello</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Qui trovi tutti i fattori considerati dal modello, i pesi applicati e lo stato di utilizzo nella previsione.
          </p>
        </header>

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
            <section className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{data.model_version}</p>
              <h2 className="mt-1 text-xl font-semibold text-slate-900">{data.title}</h2>
              <p className="mt-2 text-sm text-slate-600">{data.description}</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-700">baseline_v0_1</p>
                  <p className="mt-1 text-sm text-slate-700">
                    Modello squadra puro: usa solo statistiche storiche di team (formula invariata).
                  </p>
                </div>
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
                    baseline_v0_2_player_adjusted (LIVE)
                  </p>
                  <p className="mt-1 text-sm text-emerald-950">
                    Modello live: <strong>baseline v0.1 + impatto giocatori</strong>. Non include ancora H2H, motivation o availability.
                  </p>
                </div>
              </div>
              <div className="mt-4 rounded-2xl border border-indigo-100 bg-indigo-50/70 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700">Formula expected_sot</p>
                <p className="mt-2 text-sm font-medium text-indigo-950">{data.expected_sot_formula}</p>
              </div>
            </section>

            {baseline ? (
              <section className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h3 className="text-lg font-semibold text-slate-900">{baseline.title}</h3>
                  <span className={`rounded-full px-3 py-1 text-xs font-medium ${statusBadgeClass(baseline.status)}`}>
                    {statusLabel(baseline.status)}
                  </span>
                </div>
                <p className="text-sm text-slate-600">{baseline.description}</p>
                <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
                      <tr>
                        <th className="px-3 py-2.5">Fattore</th>
                        <th className="px-3 py-2.5">Peso</th>
                        <th className="px-3 py-2.5">Stato</th>
                        <th className="px-3 py-2.5">Cosa significa</th>
                        <th className="px-3 py-2.5">Effetto sulla previsione</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {baseline.variables.map((v) => (
                        <tr key={v.technical_key}>
                          <td className="px-3 py-2">
                            <p className="font-medium text-slate-900">{v.name}</p>
                            <p className="text-xs text-slate-500">{v.technical_key}</p>
                          </td>
                          <td className="px-3 py-2">{v.weight_label ?? '—'}</td>
                          <td className="px-3 py-2">
                            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusBadgeClass(v.status)}`}>
                              {statusLabel(v.status)}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-slate-700">{v.description}</td>
                          <td className="px-3 py-2 text-slate-700">{v.interpretation}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-4 grid gap-2">
                  {baseline.variables.map((v) => {
                    const w = typeof v.weight === 'number' ? Math.max(0, Math.min(v.weight * 100, 100)) : 0
                    return (
                      <div key={`${v.technical_key}-bar`} className="rounded-xl border border-slate-200 p-3">
                        <div className="mb-1 flex justify-between text-xs text-slate-600">
                          <span>{v.name}</span>
                          <span>{v.weight_label ?? '—'}</span>
                        </div>
                        <div className="h-2 rounded-full bg-slate-100">
                          <div className="h-2 rounded-full bg-indigo-500" style={{ width: `${w}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>
            ) : null}

            {data.sections
              .filter((s) => s.id !== 'baseline_formula')
              .map((section) => (
                <section key={section.id} className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <h3 className="text-lg font-semibold text-slate-900">{section.title}</h3>
                    <span className={`rounded-full px-3 py-1 text-xs font-medium ${statusBadgeClass(section.status)}`}>
                      {statusLabel(section.status)}
                    </span>
                  </div>
                  <p className="text-sm text-slate-600">{section.description}</p>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    {section.variables.map((v) => (
                      <article key={`${section.id}-${v.technical_key}`} className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4">
                        <p className="text-sm font-semibold text-slate-900">{v.name}</p>
                        <p className="mt-1 text-xs text-slate-500">{v.technical_key}</p>
                        <p className="mt-2 text-sm text-slate-700">{v.description}</p>
                        <p className="mt-2 text-xs text-slate-600"><strong>Impatto:</strong> {v.impact}</p>
                        <p className="mt-1 text-xs text-slate-600"><strong>Lettura semplice:</strong> {v.interpretation}</p>
                      </article>
                    ))}
                  </div>
                  {section.id === 'player_impact' ? (
                    <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50/90 px-3 py-2 text-xs text-amber-950">
                      <strong>Applicato nel modello live v0.2 Player Adjusted</strong>
                      <br />
                      <strong>Non applicato nella baseline storica v0.1</strong>
                    </p>
                  ) : null}
                  {(section.id === 'h2h' || section.id === 'match_context') ? (
                    <p className="mt-4 rounded-xl border border-slate-200 bg-slate-100/70 px-3 py-2 text-xs text-slate-700">
                      Visibile nella card partita, ma non ancora incluso matematicamente.
                    </p>
                  ) : null}
                  {section.id === 'confidence' ? (
                    <div className="mt-4 grid gap-2 sm:grid-cols-3">
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50/80 p-3 text-xs text-emerald-900">MAE sotto 1.50 = buono</div>
                      <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-3 text-xs text-amber-900">MAE 1.50-2.00 = accettabile</div>
                      <div className="rounded-xl border border-rose-200 bg-rose-50/80 p-3 text-xs text-rose-900">MAE sopra 2.00 = da migliorare</div>
                    </div>
                  ) : null}
                </section>
              ))}
          </>
        ) : null}
      </div>
    </div>
  )
}
