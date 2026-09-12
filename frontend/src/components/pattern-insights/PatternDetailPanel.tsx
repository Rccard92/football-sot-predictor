import { useEffect, useState } from 'react'
import { getPatternDetail, type PatternDetail } from '../../lib/patternInsightsApi'
import { heatBg } from './PatternInsightsShell'

function pct(v: number | null | undefined, d = 1): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(d)}%`
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

export function PatternDetailPanel({
  candidateId,
  onClose,
}: {
  candidateId: number
  onClose: () => void
}) {
  const [data, setData] = useState<PatternDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'leagues' | 'matches'>('leagues')

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    getPatternDetail(candidateId)
      .then((d) => {
        if (alive) setData(d)
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : 'Errore caricamento dettaglio')
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [candidateId])

  const isMarket = data?.candidate.target_type === 'market'
  const maxProfit = Math.max(1, ...(data?.by_competition ?? []).map((l) => Math.abs(l.profit_units ?? 0)))

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-auto p-4"
      style={{ background: 'rgba(4,8,16,0.72)' }}
      onClick={onClose}
    >
      <div
        className="pi-root my-6 w-full max-w-5xl"
        style={{ minHeight: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <div className="pi-section-title">Dettaglio pattern</div>
            {data && (
              <>
                <div className="mt-1 text-base font-semibold">{data.candidate.target_label}</div>
                <div className="mt-0.5 text-xs" style={{ color: 'var(--pi-muted)' }}>
                  {data.candidate.filters_text_human}
                </div>
              </>
            )}
          </div>
          <button type="button" className="pi-btn" onClick={onClose}>
            Chiudi ✕
          </button>
        </div>

        {loading && (
          <div className="text-sm" style={{ color: 'var(--pi-muted)' }}>
            Caricamento dettaglio…
          </div>
        )}
        {error && (
          <div className="text-sm" style={{ color: 'var(--pi-neg)' }}>
            {error}
          </div>
        )}

        {data && (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
              <div className="pi-tile">
                <div className="text-[10px] uppercase" style={{ color: 'var(--pi-muted)' }}>
                  Partite
                </div>
                <div className="text-lg font-bold tabular-nums">{data.overall.n}</div>
              </div>
              <div className="pi-tile">
                <div className="text-[10px] uppercase" style={{ color: 'var(--pi-muted)' }}>
                  Esiti
                </div>
                <div className="text-lg font-bold tabular-nums">
                  {data.overall.wins}V · {data.overall.losses}P
                </div>
              </div>
              <div className="pi-tile">
                <div className="text-[10px] uppercase" style={{ color: 'var(--pi-muted)' }}>
                  Win rate
                </div>
                <div className="text-lg font-bold tabular-nums">
                  {data.overall.win_rate_pct?.toFixed(1)}%
                </div>
              </div>
              {isMarket ? (
                <>
                  <div className="pi-tile">
                    <div className="text-[10px] uppercase" style={{ color: 'var(--pi-muted)' }}>
                      ROI
                    </div>
                    <div
                      className="text-lg font-bold tabular-nums"
                      style={{ color: 'var(--pi-pos)' }}
                    >
                      {pct(data.overall.roi_pct)}
                    </div>
                  </div>
                  <div className="pi-tile">
                    <div className="text-[10px] uppercase" style={{ color: 'var(--pi-muted)' }}>
                      Profitto
                    </div>
                    <div className="text-lg font-bold tabular-nums">
                      {data.overall.profit_units?.toFixed(1)} u
                    </div>
                  </div>
                  <div className="pi-tile">
                    <div className="text-[10px] uppercase" style={{ color: 'var(--pi-muted)' }}>
                      Quota media
                    </div>
                    <div className="text-lg font-bold tabular-nums">
                      {data.overall.avg_quota?.toFixed(2)}
                    </div>
                  </div>
                </>
              ) : (
                <div className="pi-tile sm:col-span-2">
                  <div className="text-[10px] uppercase" style={{ color: 'var(--pi-muted)' }}>
                    Frequenza base
                  </div>
                  <div className="text-lg font-bold tabular-nums">
                    {data.candidate.baseline_win_rate_pct?.toFixed(1)}%
                  </div>
                </div>
              )}
            </div>

            <div
              className="mt-3 rounded-xl border px-3 py-2 text-[11px] leading-relaxed"
              style={{
                borderColor: 'rgba(53,224,196,0.25)',
                background: 'rgba(53,224,196,0.06)',
                color: 'var(--pi-muted)',
              }}
            >
              Il pattern e&apos; favorevole in{' '}
              <strong style={{ color: 'var(--pi-text)' }}>
                {data.concentration.leagues_favourable} campionati su{' '}
                {data.concentration.leagues_with_sample}
              </strong>{' '}
              con almeno {data.concentration.min_league_sample} partite
              {data.concentration.top_league_profit_share_pct != null && (
                <>
                  {' '}
                  · il campionato migliore da solo pesa{' '}
                  <strong style={{ color: 'var(--pi-text)' }}>
                    {data.concentration.top_league_profit_share_pct}%
                  </strong>{' '}
                  del profitto totale
                </>
              )}
              . Se il profitto e&apos; concentrato in una o due leghe, il pattern non e&apos;
              generale: e&apos; una caratteristica di quei campionati (o fortuna).
            </div>

            <div className="mt-3 flex gap-2">
              <button
                type="button"
                className="pi-btn"
                style={tab === 'leagues' ? { borderColor: 'var(--pi-accent)', color: 'var(--pi-accent)' } : undefined}
                onClick={() => setTab('leagues')}
              >
                Per campionato ({data.by_competition.length})
              </button>
              <button
                type="button"
                className="pi-btn"
                style={tab === 'matches' ? { borderColor: 'var(--pi-accent)', color: 'var(--pi-accent)' } : undefined}
                onClick={() => setTab('matches')}
              >
                Partite attivate ({data.matches_total})
              </button>
            </div>

            {tab === 'leagues' && (
              <div className="pi-scroll mt-3" style={{ maxHeight: 420 }}>
                <table className="pi-table">
                  <thead>
                    <tr>
                      <th>Campionato</th>
                      <th>Partite</th>
                      <th>Esiti</th>
                      <th>Win rate</th>
                      {isMarket ? <th>ROI</th> : <th>Scarto</th>}
                      {isMarket ? <th>Profitto</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_competition.map((l) => (
                      <tr key={l.competition} style={{ opacity: l.enough_sample ? 1 : 0.45 }}>
                        <td className="font-semibold">
                          {l.competition}
                          {!l.enough_sample && (
                            <span className="ml-1 text-[10px]" style={{ color: 'var(--pi-muted)' }}>
                              (campione minimo)
                            </span>
                          )}
                        </td>
                        <td className="tabular-nums">{l.n}</td>
                        <td className="tabular-nums">
                          {l.wins}V · {l.losses}P
                        </td>
                        <td className="tabular-nums">{l.win_rate_pct?.toFixed(1)}%</td>
                        <td
                          className="tabular-nums font-semibold"
                          style={{
                            color:
                              (isMarket ? l.roi_pct ?? 0 : l.deviation_pct ?? 0) >= 0
                                ? 'var(--pi-pos)'
                                : 'var(--pi-neg)',
                          }}
                        >
                          {pct(isMarket ? l.roi_pct : l.deviation_pct)}
                        </td>
                        {isMarket ? (
                          <td
                            className="tabular-nums"
                            style={{
                              background: heatBg(
                                l.profit_units,
                                maxProfit,
                                (l.profit_units ?? 0) >= 0,
                              ),
                            }}
                          >
                            {l.profit_units?.toFixed(1)} u
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {tab === 'matches' && (
              <div className="pi-scroll mt-3" style={{ maxHeight: 420 }}>
                <table className="pi-table">
                  <thead>
                    <tr>
                      <th>Data</th>
                      <th>Campionato</th>
                      <th>Partita</th>
                      <th>Esito</th>
                      {isMarket ? <th>Quota</th> : <th>Valore reale</th>}
                      {isMarket ? <th>P/L</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {data.matches.map((m) => (
                      <tr key={m.lab_match_id}>
                        <td className="whitespace-nowrap tabular-nums">{fmtDate(m.kickoff_at)}</td>
                        <td className="whitespace-nowrap">{m.competition}</td>
                        <td className="whitespace-nowrap font-semibold">
                          {m.home_team} – {m.away_team}
                        </td>
                        <td
                          className="whitespace-nowrap font-semibold"
                          style={{ color: m.won ? 'var(--pi-pos)' : 'var(--pi-neg)' }}
                        >
                          {m.won ? 'Vinta' : 'Persa'}
                        </td>
                        <td className="tabular-nums">
                          {isMarket
                            ? (m.quota_book?.toFixed(2) ?? '—')
                            : (m.actual_value ?? '—')}
                        </td>
                        {isMarket ? (
                          <td
                            className="tabular-nums"
                            style={{
                              color: (m.profit_1u ?? 0) >= 0 ? 'var(--pi-pos)' : 'var(--pi-neg)',
                            }}
                          >
                            {m.profit_1u != null ? `${m.profit_1u > 0 ? '+' : ''}${m.profit_1u.toFixed(2)}` : '—'}
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {data.matches_truncated && (
                  <div className="p-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
                    Mostrate le prime {data.matches.length} partite su {data.matches_total}.
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
