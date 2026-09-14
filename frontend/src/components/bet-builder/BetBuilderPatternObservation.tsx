import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getLiveObservation, groupLabel, type LiveObservationGroupItem } from '../../lib/cecchinoLiveApi'
import { MARKET_LABELS } from '../../lib/masterPatternApi'
import { formatFetchError } from '../../utils/formatFetchError'

function signed(v: number | null | undefined, suffix = '%'): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toLocaleString('it-IT', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}${suffix}`
}

/** Pattern Master V2.5 accesi nel giorno, un segnale per mercato: in osservazione, mai aggiunti al carrello. */
export function BetBuilderPatternObservation({ date }: { date: string }) {
  const [items, setItems] = useState<LiveObservationGroupItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let alive = true
    setItems(null)
    setError(null)
    getLiveObservation(date)
      .then((d) => alive && setItems(d.groups ?? []))
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
          {error ? 'errore' : items == null ? '…' : `${count} ${count === 1 ? 'segnale' : 'segnali'}`}
        </span>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-4 py-3">
          {error && <p className="text-sm text-red-700">{error}</p>}
          {items && items.length === 0 && (
            <p className="text-sm text-slate-500">Nessun pattern acceso sulle partite registrate di questa giornata.</p>
          )}
          {items && items.length > 0 && (
            <>
              <p className="mb-2 text-xs text-slate-500">
                Un segnale = un mercato su una partita, con il numero di pattern concordi.{' '}
                <Link to="/osservazione-live" className="font-medium text-slate-700 underline">
                  Andamento nel tempo
                </Link>
              </p>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                      <th className="py-2 pr-2 font-medium">Partita</th>
                      <th className="py-2 pr-2 font-medium">Mercato</th>
                      <th className="py-2 pr-2 text-right font-medium">Pattern</th>
                      <th className="py-2 pr-2 text-right font-medium">Storico</th>
                      <th className="py-2 pr-2 text-right font-medium">Quota</th>
                      <th className="py-2 font-medium">Esito</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => {
                      const g = it.group
                      const isMarket = g.target_type === 'market'
                      return (
                        <tr key={`${it.today_fixture_id}-${g.key}`} className="border-b border-slate-100 align-top">
                          <td className="py-2 pr-2">
                            <div className="font-medium text-slate-900">
                              {it.home_team_name} – {it.away_team_name}
                            </div>
                            <div className="text-xs text-slate-500">
                              {it.league_name}
                              {it.kickoff ? ` · ${new Date(it.kickoff).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}` : ''}
                            </div>
                          </td>
                          <td className="py-2 pr-2 font-medium text-slate-900">{groupLabel(g, MARKET_LABELS)}</td>
                          <td className="py-2 pr-2 text-right tabular-nums text-slate-700">{g.patterns_count}</td>
                          <td className="py-2 pr-2 text-right text-xs tabular-nums text-slate-700">
                            {isMarket
                              ? `miglior ROI ${signed(g.hist_roi_pct_best)}`
                              : `${g.hist_win_rate_pct == null ? '—' : Math.round(g.hist_win_rate_pct)}% · scarto ${signed(g.hist_deviation_pct, ' pt')}`}
                          </td>
                          <td className="py-2 pr-2 text-right tabular-nums">{isMarket ? (g.quota_book ?? '—') : '—'}</td>
                          <td className="py-2 text-slate-700">
                            {it.result?.won == null ? (it.status === 'settled' ? '—' : 'In attesa') : it.result.won ? 'Vinta' : 'Persa'}
                            {it.result?.actual != null && <span className="text-xs text-slate-500"> ({it.result.actual})</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  )
}
