import { useCallback, useState } from 'react'

import type { CecchinoApiRawInspectorResponse } from '../../lib/cecchinoTodayApi'
import { getApiRawInspector } from '../../lib/cecchinoTodayApi'

type Props = {
  todayFixtureId?: number
}

function boolLabel(v?: boolean): string {
  if (v === true) return 'Sì'
  if (v === false) return 'No'
  return '—'
}

function fmtVal(v: unknown): string {
  if (v == null || v === '') return '—'
  return String(v)
}

export function CecchinoApiRawInspectorPanel({ todayFixtureId }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<CecchinoApiRawInspectorResponse | null>(null)
  const [lastForceRefresh, setLastForceRefresh] = useState(false)

  const runInspect = useCallback(
    async (opts: { forceRefresh: boolean; includeRaw: boolean }) => {
      if (!todayFixtureId) return
      setLoading(true)
      setError(null)
      setLastForceRefresh(opts.forceRefresh)
      try {
        const res = await getApiRawInspector(todayFixtureId, {
          forceRefresh: opts.forceRefresh,
          includeRaw: opts.includeRaw,
        })
        setData(res)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Errore ispezione API raw')
        setData(null)
      } finally {
        setLoading(false)
      }
    },
    [todayFixtureId],
  )

  if (!todayFixtureId) return null

  const mapping = data?.suggested_xg_mapping
  const mappingFields = [
    { key: 'home_xg_for', label: 'home_xg_for' },
    { key: 'away_xg_for', label: 'away_xg_for' },
    { key: 'home_xg_against', label: 'home_xg_against' },
    { key: 'away_xg_against', label: 'away_xg_against' },
  ] as const

  return (
    <details className="rounded-lg border border-slate-300 bg-slate-50 text-sm">
      <summary className="cursor-pointer px-4 py-3 font-medium text-slate-800 hover:bg-slate-100">
        API Raw Inspector — Ispeziona dati API
      </summary>
      <div className="space-y-4 border-t border-slate-200 px-4 py-4">
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950">
          L&apos;ispezione API live può consumare chiamate del provider. Usarla solo manualmente.
        </p>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={loading}
            onClick={() => void runInspect({ forceRefresh: false, includeRaw: false })}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-100 disabled:opacity-50"
          >
            Ispeziona cache
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => void runInspect({ forceRefresh: true, includeRaw: false })}
            className="rounded-md border border-orange-300 bg-orange-50 px-3 py-1.5 text-xs font-medium text-orange-950 hover:bg-orange-100 disabled:opacity-50"
          >
            Ispeziona API live
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => void runInspect({ forceRefresh: lastForceRefresh, includeRaw: true })}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            Mostra JSON completo
          </button>
        </div>

        {loading && <p className="text-xs text-slate-500">Caricamento ispezione…</p>}
        {error && <p className="text-xs text-red-700">{error}</p>}

        {data && (
          <>
            <div className="rounded-md border border-slate-200 bg-white px-3 py-3 text-xs">
              <p className="font-semibold text-slate-800">Riepilogo fixture</p>
              <dl className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
                <div>
                  <dt className="text-slate-500">Match</dt>
                  <dd>{data.fixture?.match ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">provider_fixture_id</dt>
                  <dd className="tabular-nums">{fmtVal(data.fixture?.provider_fixture_id)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">League</dt>
                  <dd>{data.fixture?.league ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Season</dt>
                  <dd className="tabular-nums">{fmtVal(data.fixture?.season)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">today_fixture_id</dt>
                  <dd className="tabular-nums">{fmtVal(data.ids?.today_fixture_id)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Status</dt>
                  <dd>{data.status ?? '—'}</dd>
                </div>
              </dl>
            </div>

            {(data.sources_checked?.length ?? 0) > 0 && (
              <div className="overflow-x-auto">
                <p className="mb-2 text-xs font-semibold text-slate-700">Fonti controllate</p>
                <table className="min-w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="px-2 py-2 font-medium">Fonte</th>
                      <th className="px-2 py-2 font-medium">Disponibile</th>
                      <th className="px-2 py-2 font-medium">Origine</th>
                      <th className="px-2 py-2 font-medium">Chiamato</th>
                      <th className="px-2 py-2 font-medium">Record</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.sources_checked?.map((row) => (
                      <tr key={row.key} className="border-b border-slate-100">
                        <td className="px-2 py-2">{row.label ?? row.key}</td>
                        <td className="px-2 py-2">{boolLabel(row.available)}</td>
                        <td className="px-2 py-2">{row.origin ?? '—'}</td>
                        <td className="px-2 py-2">{boolLabel(row.called)}</td>
                        <td className="px-2 py-2 tabular-nums">{row.records_count ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="overflow-x-auto">
              <p className="mb-2 text-xs font-semibold text-slate-700">Campi xG / expected trovati</p>
              {(data.matches_found?.length ?? 0) === 0 ? (
                <p className="text-xs text-slate-500">Nessun campo xG/expected trovato.</p>
              ) : (
                <table className="min-w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="px-2 py-2 font-medium">Endpoint</th>
                      <th className="px-2 py-2 font-medium">Team</th>
                      <th className="px-2 py-2 font-medium">Path</th>
                      <th className="px-2 py-2 font-medium">Type/Key</th>
                      <th className="px-2 py-2 font-medium">Valore</th>
                      <th className="px-2 py-2 font-medium">Keyword</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.matches_found?.map((row, i) => (
                      <tr key={`${row.path}-${i}`} className="border-b border-slate-100 align-top">
                        <td className="px-2 py-2">{row.endpoint ?? '—'}</td>
                        <td className="px-2 py-2">
                          {row.team?.name ?? row.team?.side ?? '—'}
                        </td>
                        <td className="max-w-[140px] truncate px-2 py-2" title={row.path}>
                          {row.path ?? '—'}
                        </td>
                        <td className="px-2 py-2">{fmtVal(row.type ?? row.key)}</td>
                        <td className="px-2 py-2 tabular-nums">{fmtVal(row.value)}</td>
                        <td className="px-2 py-2">{row.matched_keyword ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {mapping && (
              <div className="rounded-md border border-teal-200 bg-teal-50 px-3 py-3 text-xs">
                <p className="font-semibold text-teal-950">
                  Suggested mapping ({mapping.status ?? '—'})
                </p>
                {mapping.status === 'not_found' ? (
                  <p className="mt-2 text-teal-900">{(mapping.warnings ?? []).join(', ') || 'Nessun mapping suggerito.'}</p>
                ) : (
                  <table className="mt-2 min-w-full text-left">
                    <thead>
                      <tr className="text-teal-800">
                        <th className="px-2 py-1 font-medium">Campo</th>
                        <th className="px-2 py-1 font-medium">Valore</th>
                        <th className="px-2 py-1 font-medium">Fonte</th>
                        <th className="px-2 py-1 font-medium">Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mappingFields.map(({ key, label }) => {
                        const field = mapping[key]
                        return (
                          <tr key={key} className="border-t border-teal-200/60">
                            <td className="px-2 py-1 font-medium">{label}</td>
                            <td className="px-2 py-1 tabular-nums">{fmtVal(field?.value)}</td>
                            <td className="px-2 py-1">{field?.source ?? '—'}</td>
                            <td className="px-2 py-1">{field?.confidence ?? '—'}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {data.api_usage && (
              <p className="text-xs text-slate-500">
                Chiamate API: {data.api_usage.external_calls_made ?? 0} —{' '}
                {(data.api_usage.endpoints_called ?? []).join(', ') || 'nessuna'}
              </p>
            )}

            {(data.warnings?.length ?? 0) > 0 && (
              <p className="text-xs text-amber-800">Warning: {data.warnings?.join(', ')}</p>
            )}

            <details className="rounded-md border border-slate-200 bg-white">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-slate-700">
                JSON inspector
              </summary>
              <pre className="max-h-96 overflow-auto border-t border-slate-200 bg-slate-950 p-3 text-[10px] text-slate-100">
                {JSON.stringify(data, null, 2)}
              </pre>
            </details>
          </>
        )}
      </div>
    </details>
  )
}
