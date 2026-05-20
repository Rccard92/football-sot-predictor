import type { SportApiPlayerMatchRow } from '../../types/lineupImpact'

function recBadge(rec: string) {
  switch (rec) {
    case 'AUTO_SAFE':
      return 'bg-emerald-100 text-emerald-900 border-emerald-200'
    case 'REVIEW':
      return 'bg-amber-100 text-amber-950 border-amber-200'
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200'
  }
}

export function SportApiPlayerMatchingPanel({
  matches,
  compact = false,
}: {
  matches: SportApiPlayerMatchRow[]
  compact?: boolean
}) {
  if (matches.length === 0) {
    return (
      <p className="text-xs text-slate-500">Nessun giocatore SportAPI da mappare (importa prima le lineups).</p>
    )
  }

  return (
    <div className={compact ? 'space-y-2' : 'space-y-3'}>
      <h3 className="text-xs font-semibold text-slate-800">Mapping giocatori SportAPI ↔ API-Sports</h3>
      <div className="max-h-72 overflow-auto rounded-lg border border-slate-200">
        <table className="w-full text-left text-[10px]">
          <thead className="sticky top-0 bg-slate-100 text-slate-600">
            <tr>
              <th className="px-2 py-1.5">SportAPI</th>
              <th className="px-2 py-1.5">API-Sports</th>
              <th className="px-2 py-1.5">Score</th>
              <th className="px-2 py-1.5">Stato</th>
              <th className="px-2 py-1.5">Lato</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={`${m.sportapi_player_id}-${m.team_side}-${m.is_missing}`} className="border-t border-slate-100">
                <td className="px-2 py-1.5">
                  <span className="font-medium text-slate-900">{m.sportapi_player_name}</span>
                  {m.is_missing ? (
                    <span className="ml-1 text-rose-600">(indisponibile)</span>
                  ) : null}
                </td>
                <td className="px-2 py-1.5 text-slate-700">
                  {m.api_sports_player_name ?? '—'}
                </td>
                <td className="px-2 py-1.5 font-mono">{m.confidence_score}</td>
                <td className="px-2 py-1.5">
                  <span
                    className={`inline-flex rounded border px-1 py-px text-[9px] font-medium ${recBadge(m.recommendation)}`}
                  >
                    {m.recommendation}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-slate-500">{m.team_side ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-slate-500">
        Mapping con score &lt; 90 non salvato automaticamente. Statistiche SOT da API-Football (
        player_sot_profiles).
      </p>
    </div>
  )
}
