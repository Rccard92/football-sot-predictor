import type { DrawCredibilityDebugSample } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  samples: DrawCredibilityDebugSample[]
}

export function DrawCredibilityDebugPanel({ samples }: Props) {
  if (samples.length === 0) return null

  return (
    <details className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <summary className="cursor-pointer text-sm font-semibold text-slate-900">
        Debug — esempi fixture escluse ({samples.length})
      </summary>
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="px-2 py-1">ID</th>
              <th className="px-2 py-1">Data</th>
              <th className="px-2 py-1">Partita</th>
              <th className="px-2 py-1">Campionato</th>
              <th className="px-2 py-1">Motivo</th>
            </tr>
          </thead>
          <tbody>
            {samples.map((s) => (
              <tr key={`${s.today_fixture_id}-${s.reason}`} className="border-t border-slate-100">
                <td className="px-2 py-1 tabular-nums">{s.today_fixture_id}</td>
                <td className="px-2 py-1">{s.scan_date ?? '—'}</td>
                <td className="px-2 py-1">
                  {s.home_team ?? '?'} vs {s.away_team ?? '?'}
                </td>
                <td className="px-2 py-1">{s.league_name ?? '—'}</td>
                <td className="px-2 py-1 font-mono text-slate-600">{s.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
