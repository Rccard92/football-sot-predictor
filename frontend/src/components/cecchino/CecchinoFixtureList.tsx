import type { CecchinoUpcomingFixtureRow } from '../../lib/api'

type Props = {
  fixtures: CecchinoUpcomingFixtureRow[]
  selectedFixtureId: number | null
  onSelect: (fixtureId: number) => void
}

function fmtKickoff(iso: string | null) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function CecchinoFixtureList({ fixtures, selectedFixtureId, onSelect }: Props) {
  if (fixtures.length === 0) {
    return (
      <p className="text-sm text-slate-600">Nessuna partita upcoming per questo campionato.</p>
    )
  }

  return (
    <ul className="space-y-2">
      {fixtures.map((row) => {
        const id = row.fixture.fixture_id
        const active = selectedFixtureId === id
        return (
          <li key={id}>
            <button
              type="button"
              onClick={() => onSelect(id)}
              className={`w-full rounded-lg border px-3 py-2 text-left text-xs transition ${
                active
                  ? 'border-indigo-400 bg-indigo-50 ring-1 ring-indigo-200'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium text-slate-900">
                    {row.fixture.home_team.name} vs {row.fixture.away_team.name}
                  </p>
                  <p className="mt-0.5 text-slate-500">{fmtKickoff(row.fixture.kickoff_at)}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-0.5">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                      row.calculation_status === 'available'
                        ? 'bg-emerald-100 text-emerald-800'
                        : row.calculation_status === 'partial_low_sample'
                          ? 'bg-amber-100 text-amber-900'
                          : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {row.calculation_status ?? '—'}
                  </span>
                  {row.data_quality?.leakage_check === 'passed' && (
                    <span className="text-[9px] text-emerald-700">No leakage</span>
                  )}
                  {(row.warnings || []).some((w) => w.startsWith('low_sample')) && (
                    <span className="text-[9px] text-amber-700">Campione basso</span>
                  )}
                </div>
              </div>
              {row.final_quota_1 != null && (
                <p className="mt-1 tabular-nums text-slate-600">
                  Finale: 1 {row.final_quota_1?.toFixed(2)} · X {row.final_quota_x?.toFixed(2) ?? '—'} · 2{' '}
                  {row.final_quota_2?.toFixed(2) ?? '—'}
                </p>
              )}
            </button>
          </li>
        )
      })}
    </ul>
  )
}
