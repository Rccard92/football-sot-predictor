import type { StarterFieldForceRow } from '../../utils/starterFieldForce'
import { RoleBadge } from './RoleBadge'
import type { SportApiDisplayRole } from '../../types/sportapi'

function fmtNum(v: number | null, d = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(d)
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    STARTER: 'Titolare',
    BENCH: 'Panchina',
    MISSING: 'Assente',
    OUT_OF_LINEUP: 'Fuori XI',
    UNMAPPED: 'Non mappato',
  }
  return map[status] ?? status
}

function MobileCard({ row }: { row: StarterFieldForceRow }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-2.5 text-[11px]">
      <div className="flex items-center gap-2">
        <RoleBadge role={row.role as SportApiDisplayRole} />
        <span className="font-medium text-slate-900">{row.name}</span>
      </div>
      <p className="mt-1 text-slate-600">{statusLabel(row.status)}</p>
      <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-slate-700">
        <div>
          <dt className="text-[10px] text-slate-500">SOT/90</dt>
          <dd className="tabular-nums font-medium">{fmtNum(row.sot_per_90)}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-slate-500">Tiri/90</dt>
          <dd className="tabular-nums font-medium">{fmtNum(row.shots_per_90)}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-slate-500">Quota SOT</dt>
          <dd className="tabular-nums font-medium">
            {row.team_sot_share_pct != null ? `${fmtNum(row.team_sot_share_pct, 1)}%` : '—'}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] text-slate-500">Imp. off.</dt>
          <dd className="tabular-nums font-medium">{fmtNum(row.shooting_impact, 1)}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-slate-500">Imp. def.</dt>
          <dd className="tabular-nums font-medium">{fmtNum(row.defensive_impact, 2)}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-slate-500">Affidabilità</dt>
          <dd className="tabular-nums font-medium">{fmtNum(row.reliability, 0)}</dd>
        </div>
      </dl>
    </div>
  )
}

export function SportApiStartersForceTable({ rows }: { rows: StarterFieldForceRow[] }) {
  if (!rows.length) {
    return <p className="text-xs text-slate-500">Nessun titolare da mostrare.</p>
  }

  return (
    <div>
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        Forza giocatori in campo
      </p>
      <div className="space-y-2 sm:hidden">
        {rows.map((r) => (
          <MobileCard key={r.provider_player_id} row={r} />
        ))}
      </div>
      <div className="hidden overflow-x-auto sm:block">
        <table className="min-w-full text-left text-[11px] text-slate-800">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500">
              <th className="py-1.5 pr-2 font-medium">Giocatore</th>
              <th className="py-1.5 pr-2 font-medium">Ruolo</th>
              <th className="py-1.5 pr-2 font-medium">Stato</th>
              <th className="py-1.5 pr-2 font-medium">SOT/90</th>
              <th className="py-1.5 pr-2 font-medium">Tiri/90</th>
              <th className="py-1.5 pr-2 font-medium">Quota SOT</th>
              <th className="py-1.5 pr-2 font-medium">Imp. off.</th>
              <th className="py-1.5 pr-2 font-medium">Imp. def.</th>
              <th className="py-1.5 pr-2 font-medium">Affid.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.provider_player_id} className="border-b border-slate-100">
                <td className="max-w-[7rem] truncate py-1.5 pr-2 font-medium" title={r.name}>
                  {r.name}
                </td>
                <td className="py-1.5 pr-2">
                  <RoleBadge role={r.role} />
                </td>
                <td className="max-w-[5rem] py-1.5 pr-2 text-slate-600" title={r.status_note}>
                  {statusLabel(r.status)}
                </td>
                <td className="py-1.5 pr-2 tabular-nums">{fmtNum(r.sot_per_90)}</td>
                <td className="py-1.5 pr-2 tabular-nums">{fmtNum(r.shots_per_90)}</td>
                <td className="py-1.5 pr-2 tabular-nums">
                  {r.team_sot_share_pct != null ? `${fmtNum(r.team_sot_share_pct, 1)}%` : '—'}
                </td>
                <td className="py-1.5 pr-2 tabular-nums">{fmtNum(r.shooting_impact, 1)}</td>
                <td className="py-1.5 pr-2 tabular-nums">{fmtNum(r.defensive_impact, 2)}</td>
                <td className="py-1.5 pr-2 tabular-nums">{fmtNum(r.reliability, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
