import type { CecchinoFixtureDetailResponse } from '../../lib/cecchinoApi'
import { fmtKickoff } from '../../lib/cecchinoUtils'

type Props = {
  detail: CecchinoFixtureDetailResponse
}

export function CecchinoMatchBasics({ detail }: Props) {
  const { fixture } = detail
  const warnings = detail.warnings ?? []

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Partita e metadati</h3>
      <dl className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
        <div>
          <dt className="text-slate-500">Match</dt>
          <dd className="font-medium text-slate-900">
            {fixture.home_team.name} vs {fixture.away_team.name}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Kickoff</dt>
          <dd className="tabular-nums">{fmtKickoff(fixture.kickoff_at)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">competition_id</dt>
          <dd className="tabular-nums">{detail.competition_id}</dd>
        </div>
        <div>
          <dt className="text-slate-500">fixture_id</dt>
          <dd className="tabular-nums">{fixture.fixture_id}</dd>
        </div>
        <div>
          <dt className="text-slate-500">cecchino_version</dt>
          <dd>{detail.cecchino_version}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Aggiornamento</dt>
          <dd>
            {detail.updated_at ? fmtKickoff(detail.updated_at) : '—'}
            {detail.stored ? ' · in cache' : ''}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Leakage</dt>
          <dd>
            {detail.data_quality?.leakage_check === 'passed'
              ? 'passed'
              : detail.data_quality?.leakage_check === 'failed'
                ? 'failed'
                : detail.data_quality?.leakage_check ?? '—'}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Stato calcolo</dt>
          <dd>{detail.calculation_status}</dd>
        </div>
      </dl>
      {warnings.length > 0 && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <p className="text-[11px] font-semibold text-amber-900">Warning</p>
          <ul className="mt-1 list-inside list-disc text-[11px] text-amber-800">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
