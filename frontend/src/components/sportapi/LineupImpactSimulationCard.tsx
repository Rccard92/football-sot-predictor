import type { LineupImpactSimulationPayload } from '../../types/lineupImpact'
import { SportApiPlayerMatchingPanel } from './SportApiPlayerMatchingPanel'

function SideImpactBlock({ side }: { side: LineupImpactSimulationPayload['home'] }) {
  const base = side.base_expected_sot
  const adj = side.adjusted_sot_simulated
  const pct = side.impact_pct

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-slate-900">{side.team_name}</h3>
      {side.formation ? (
        <p className="text-xs text-slate-600">
          Modulo <span className="font-mono">{side.formation}</span>
        </p>
      ) : null}
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-slate-500">Base SOT</dt>
        <dd className="font-mono font-medium">{base != null ? base.toFixed(1) : '—'}</dd>
        <dt className="text-slate-500">Adjusted simulato</dt>
        <dd className="font-mono font-medium text-indigo-800">
          {adj != null ? adj.toFixed(1) : '—'}
        </dd>
        <dt className="text-slate-500">Impatto</dt>
        <dd className={pct != null && pct < 0 ? 'text-rose-700' : 'text-emerald-800'}>
          {pct != null ? `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%` : '—'}
        </dd>
        <dt className="text-slate-500">Factor</dt>
        <dd className="font-mono">{side.attacking_lineup_factor ?? '—'}</dd>
      </dl>

      {side.top5_missing && side.top5_missing.length > 0 ? (
        <div className="mt-3">
          <p className="text-[10px] font-semibold uppercase text-slate-500">Top 5 assenti</p>
          <ul className="mt-1 space-y-0.5 text-xs text-slate-800">
            {side.top5_missing.map((p) => (
              <li key={p.player_id ?? p.sportapi_player_id}>
                {p.player_name ?? p.sportapi_player_name} — share{' '}
                {p.team_sot_share_pct != null ? `${p.team_sot_share_pct}%` : '—'}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {side.top5_present && side.top5_present.length > 0 ? (
        <div className="mt-2">
          <p className="text-[10px] font-semibold uppercase text-slate-500">Top 5 presenti</p>
          <ul className="mt-1 space-y-0.5 text-xs text-slate-700">
            {side.top5_present.map((p) => (
              <li key={p.player_id ?? p.sportapi_player_id}>
                {p.player_name ?? p.sportapi_player_name}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

export function LineupImpactSimulationCard({
  data,
  showMatching = true,
}: {
  data: LineupImpactSimulationPayload | null | undefined
  showMatching?: boolean
}) {
  if (!data || data.status === 'error') {
    return null
  }

  const noLineups = !data.sportapi_lineups_available && data.status === 'no_lineups'

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold tracking-tight text-slate-900">
            Lineup Impact — Simulazione SOT
          </h2>
          <span className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-900">
            Simulazione — non usata nel modello
          </span>
          {data.confirmed === true ? (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-900">
              Peso ufficiale 100%
            </span>
          ) : (
            <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-950">
              Peso probabile 60%
            </span>
          )}
        </div>
        {data.profiles_missing ? (
          <p className="mt-1 text-[11px] text-amber-800">
            Profili player_sot_profiles assenti per questa stagione — eseguire build profili da Admin.
          </p>
        ) : null}
      </div>

      <div className="space-y-4 p-4">
        {noLineups ? (
          <p className="text-xs text-slate-600">
            Nessuna lineup SportAPI importata. La simulazione richiede dati da Admin → SportAPI Debug.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <SideImpactBlock side={data.home} />
              <SideImpactBlock side={data.away} />
            </div>

            {(data.explanation_bullets?.length ?? 0) > 0 ? (
              <div className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2">
                <p className="text-[10px] font-semibold uppercase text-slate-500">Motivi</p>
                <ul className="mt-1 list-inside list-disc text-xs text-slate-700">
                  {data.explanation_bullets!.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}

        {showMatching && (data.sportapi_player_matching?.length ?? 0) > 0 ? (
          <SportApiPlayerMatchingPanel matches={data.sportapi_player_matching!} compact />
        ) : null}
      </div>
    </section>
  )
}
