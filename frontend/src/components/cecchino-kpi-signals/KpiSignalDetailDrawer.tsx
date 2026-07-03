import type { KpiSignalActivationRow } from '../../lib/cecchinoKpiSignalsApi'
import { formatOdds } from '../cecchino-lab/signalsLabUtils'

type Props = {
  row: KpiSignalActivationRow | null
  open: boolean
  onClose: () => void
}

export function KpiSignalDetailDrawer({ row, open, onClose }: Props) {
  if (!open || !row) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button type="button" className="absolute inset-0 bg-black/30" aria-label="Chiudi" onClick={onClose} />
      <aside className="relative h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl">
        <button type="button" className="mb-4 text-sm text-slate-500" onClick={onClose}>Chiudi</button>
        <h2 className="text-lg font-bold text-slate-900">{row.home_team_name} vs {row.away_team_name}</h2>
        <p className="text-sm text-slate-600">{row.league_name} · {row.scan_date}</p>
        <dl className="mt-4 space-y-2 text-sm">
          <div><dt className="text-slate-500">Segno KPI</dt><dd className="font-medium">{row.selection_label}</dd></div>
          <div><dt className="text-slate-500">Rating</dt><dd>{row.rating_score} ({row.rating_bucket})</dd></div>
          <div><dt className="text-slate-500">Quota Book</dt><dd>{formatOdds(row.quota_book)}</dd></div>
          <div><dt className="text-slate-500">Quota Cecchino</dt><dd>{formatOdds(row.quota_cecchino)}</dd></div>
          <div><dt className="text-slate-500">Edge %</dt><dd>{row.edge_pct ?? '—'}</dd></div>
          <div><dt className="text-slate-500">Score %</dt><dd>{row.score_pct ?? '—'}</dd></div>
          <div><dt className="text-slate-500">Risultato PT</dt><dd>{row.result_home_ht ?? '—'}:{row.result_away_ht ?? '—'}</dd></div>
          <div><dt className="text-slate-500">Risultato FT</dt><dd>{row.result_home_ft ?? '—'}:{row.result_away_ft ?? '—'}</dd></div>
          <div><dt className="text-slate-500">Esito</dt><dd>{row.evaluation_status}</dd></div>
          <div><dt className="text-slate-500">Profitto (stake 1)</dt><dd>{row.profit_units ?? '—'}</dd></div>
        </dl>
      </aside>
    </div>
  )
}
