import type { LineupPlayerMappingDebugRow } from '../../types/lineupImpact'

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

function fmtNum(v: number | null | undefined, d = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(d)
}

function lineupStatusLabel(status: string | undefined): string {
  const map: Record<string, string> = {
    titolare: 'Titolare',
    panchina: 'Panchina',
    indisponibile: 'Indisponibile',
  }
  return map[status ?? ''] ?? status ?? '—'
}

export function LineupPlayerMappingDebugPanel({ rows }: { rows: LineupPlayerMappingDebugRow[] }) {
  if (!rows.length) {
    return <p className="text-xs text-slate-500">Nessun giocatore in formazione da analizzare.</p>
  }

  return (
    <div className="max-h-96 overflow-auto rounded-lg border border-slate-200">
      <table className="w-full min-w-[960px] text-left text-[10px]">
        <thead className="sticky top-0 bg-slate-100 text-slate-600">
          <tr>
            <th className="px-2 py-1.5">SportAPI</th>
            <th className="px-2 py-1.5">Squadra</th>
            <th className="px-2 py-1.5">Ruolo</th>
            <th className="px-2 py-1.5">Stato</th>
            <th className="px-2 py-1.5">Profilo match</th>
            <th className="px-2 py-1.5">Profile ID</th>
            <th className="px-2 py-1.5">Score</th>
            <th className="px-2 py-1.5">Stato match</th>
            <th className="px-2 py-1.5">SOT/90</th>
            <th className="px-2 py-1.5">Quota SOT</th>
            <th className="px-2 py-1.5">Impact</th>
            <th className="px-2 py-1.5">Affid.</th>
            <th className="px-2 py-1.5">Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, idx) => (
            <tr key={`${r.sportapi_player_name}-${r.team_side}-${idx}`} className="border-t border-slate-100">
              <td className="px-2 py-1.5 font-medium text-slate-900">{r.sportapi_player_name ?? '—'}</td>
              <td className="px-2 py-1.5 text-slate-700">{r.team_name ?? '—'}</td>
              <td className="px-2 py-1.5 text-slate-600">{r.role ?? '—'}</td>
              <td className="px-2 py-1.5 text-slate-600">{lineupStatusLabel(r.lineup_status)}</td>
              <td className="px-2 py-1.5 text-slate-700">{r.matched_profile_name ?? '—'}</td>
              <td className="px-2 py-1.5 font-mono text-[9px] text-slate-500">
                {r.player_profile_id ? r.player_profile_id.slice(0, 8) + '…' : '—'}
              </td>
              <td className="px-2 py-1.5 font-mono">{fmtNum(r.match_score, 1)}</td>
              <td className="px-2 py-1.5">
                <span
                  className={`inline-flex rounded border px-1 py-px text-[9px] font-medium ${recBadge(String(r.match_status ?? 'NO_MATCH'))}`}
                >
                  {r.match_status ?? 'NO_MATCH'}
                </span>
              </td>
              <td className="px-2 py-1.5 font-mono">{fmtNum(r.shots_on_per90)}</td>
              <td className="px-2 py-1.5 font-mono">
                {r.team_sot_share != null ? `${fmtNum(r.team_sot_share * 100, 1)}%` : '—'}
              </td>
              <td className="px-2 py-1.5 font-mono">{fmtNum(r.shooting_impact_score, 1)}</td>
              <td className="px-2 py-1.5 font-mono">{fmtNum(r.reliability_score, 0)}</td>
              <td className="max-w-[140px] px-2 py-1.5 text-slate-500">{r.reason ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
