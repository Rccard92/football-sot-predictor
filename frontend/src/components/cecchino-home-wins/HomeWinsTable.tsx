import {
  availabilityBadgeLabel,
  type HomeWinsListItem,
} from '../../lib/cecchinoHomeWinsApi'

type Props = {
  items: HomeWinsListItem[]
  loading?: boolean
  onOpenDetail: (id: number) => void
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' })
  } catch {
    return iso
  }
}

function AvailBadge({ status }: { status: string }) {
  const ok = status === 'available'
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
        ok
          ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
          : 'bg-slate-100 text-slate-500 ring-1 ring-slate-200'
      }`}
    >
      {availabilityBadgeLabel(status)}
    </span>
  )
}

function CompletenessBadge({ status }: { status: string }) {
  const complete = status === 'complete'
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
        complete
          ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-200'
          : 'bg-amber-50 text-amber-800 ring-1 ring-amber-200'
      }`}
    >
      {complete ? 'Completo' : 'Parziale'}
    </span>
  )
}

export function HomeWinsTable({ items, loading, onOpenDetail }: Props) {
  if (loading && items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500 shadow-sm">
        Caricamento partite…
      </div>
    )
  }
  if (!loading && items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center shadow-sm">
        <p className="text-sm font-medium text-slate-800">Nessuna vittoria casalinga</p>
        <p className="mt-1 text-sm text-slate-500">
          Nessuna partita finished con esito reale 1 per i filtri selezionati.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-3">Data</th>
              <th className="px-3 py-3">Competizione</th>
              <th className="px-3 py-3">Partita</th>
              <th className="px-3 py-3">FT</th>
              <th className="px-3 py-3">HT</th>
              <th className="px-3 py-3">Diff</th>
              <th className="px-3 py-3">KPI</th>
              <th className="px-3 py-3">Equilibrio</th>
              <th className="px-3 py-3">Intensità Goal</th>
              <th className="px-3 py-3">Completezza</th>
              <th className="px-3 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((item) => (
              <tr key={item.today_fixture_id} className="hover:bg-slate-50/80">
                <td className="whitespace-nowrap px-3 py-2.5 text-slate-700">
                  {fmtDate(item.kickoff || item.scan_date)}
                </td>
                <td className="px-3 py-2.5 text-slate-700">
                  <div className="font-medium">{item.league || '—'}</div>
                  <div className="text-xs text-slate-500">{item.country || ''}</div>
                </td>
                <td className="px-3 py-2.5 font-medium text-slate-900">
                  {item.home_team || '—'} – {item.away_team || '—'}
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 tabular-nums font-semibold text-slate-900">
                  {item.ft_home}-{item.ft_away}
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-slate-600">
                  {item.ht_home != null && item.ht_away != null
                    ? `${item.ht_home}-${item.ht_away}`
                    : '—'}
                </td>
                <td className="px-3 py-2.5 tabular-nums text-slate-700">+{item.goal_difference}</td>
                <td className="px-3 py-2.5">
                  <AvailBadge status={item.kpi_availability} />
                </td>
                <td className="px-3 py-2.5">
                  <AvailBadge status={item.balance_availability} />
                </td>
                <td className="px-3 py-2.5">
                  <AvailBadge status={item.goal_intensity_availability} />
                </td>
                <td className="px-3 py-2.5">
                  <CompletenessBadge status={item.completeness_status} />
                </td>
                <td className="px-3 py-2.5 text-right">
                  <button
                    type="button"
                    onClick={() => onOpenDetail(item.today_fixture_id)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
                  >
                    Dettaglio
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
