import { useEffect, useState } from 'react'
import { getLiveObservation, type LiveObservationItem } from '../../lib/cecchinoLiveApi'
import { MARKET_LABELS } from '../../lib/masterPatternApi'
import { formatFetchError } from '../../utils/formatFetchError'

function signed(v: number | null | undefined, suffix = '%'): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toLocaleString('it-IT', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}${suffix}`
}

/** Pattern Master V2.5 accesi nel giorno: in osservazione, mai aggiunti al carrello. */
export function BetBuilderPatternObservation({ date }: { date: string }) {
  const [items, setItems] = useState<LiveObservationItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let alive = true
    setItems(null)
    setError(null)
    getLiveObservation(date)
      .then((d) => alive && setItems(d.items))
      .catch((e) => alive && setError(formatFetchError(e)))
    return () => {
      alive = false
    }
  }, [date])

  const count = items?.length ?? 0
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="bet-builder-pattern-observation">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span>
          <span className="text-sm font-semibold text-slate-900">Pattern Master in osservazione</span>
          <span className="ml-2 text-xs text-slate-500">
            V2.5 · registrati prima del calcio d&apos;inizio · nessuna giocata automatica
          </span>
        </span>
        <span className="text-xs font-medium tabular-nums text-slate-600">
          {error ? 'errore' : items == null ? '…' : `${count} ${count === 1 ? 'pattern' : 'pattern'}`}
        </span>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-4 py-3">
          {error && <p className="text-sm text-red-700">{error}</p>}
          {items && items.length === 0 && (
            <p className="text-sm text-slate-500">Nessun pattern acceso sulle partite registrate di questa giornata.</p>
          )}
          {items && items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                    <th className="py-2 pr-2 font-medium">Partita</th>
                    <th className="py-2 pr-2 font-medium">Mercato</th>
                    <th className="py-2 pr-2 font-medium">Condizioni</th>
                    <th className="py-2 pr-2 text-right font-medium">Storico</th>
                    <th className="py-2 pr-2 text-right font-medium">Quota</th>
                    <th className="py-2 font-medium">Esito</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it) => {
                    const p = it.pattern
                    const isMarket = p.target_type === 'market'
                    return (
                      <tr key={`${it.today_fixture_id}-${p.id}`} className="border-b border-slate-100 align-top">
                        <td className="py-2 pr-2">
                          <div className="font-medium text-slate-900">
                            {it.home_team_name} – {it.away_team_name}
                          </div>
                          <div className="text-xs text-slate-500">
                            {it.league_name}
                            {it.kickoff ? ` · ${new Date(it.kickoff).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}` : ''}
                          </div>
                        </td>
                        <td className="py-2 pr-2 font-medium text-slate-900">
                          {isMarket ? (MARKET_LABELS[p.target_key] ?? p.market_label) : p.market_label}
                        </td>
                        <td className="py-2 pr-2 text-xs text-slate-600">{p.conditions_text}</td>
                        <td className="py-2 pr-2 text-right text-xs tabular-nums text-slate-700">
                          {isMarket ? `ROI ${signed(p.roi_pct)}` : `scarto ${signed(p.avg_deviation_pct, ' pt')}`}
                          <div className="text-slate-500">{p.total_n} partite</div>
                        </td>
                        <td className="py-2 pr-2 text-right tabular-nums">{p.quota_book ?? '—'}</td>
                        <td className="py-2 text-slate-700">
                          {it.result?.won == null ? (it.status === 'settled' ? '—' : 'In attesa') : it.result.won ? 'Vinta' : 'Persa'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
