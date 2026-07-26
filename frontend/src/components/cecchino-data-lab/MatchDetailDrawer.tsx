import { useEffect, useState } from 'react'
import { formatOdd, getCecchinoLabMatch, type CecchinoLabMatchDetail } from '../../lib/cecchinoLabApi'
import { qualityLabel } from './labTheme'

type Props = {
  matchId: number | null
  onClose: () => void
}

export function MatchDetailDrawer({ matchId, onClose }: Props) {
  const [detail, setDetail] = useState<CecchinoLabMatchDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [rawOpen, setRawOpen] = useState(false)

  useEffect(() => {
    if (matchId == null) return
    let cancelled = false
    getCecchinoLabMatch(matchId)
      .then((d) => {
        if (!cancelled) {
          setDetail(d)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDetail(null)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [matchId])

  if (matchId == null) return null

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/45" onClick={onClose}>
      <aside
        className="flex h-full w-full max-w-xl flex-col overflow-y-auto border-l shadow-2xl"
        style={{ background: 'var(--lab-bg-elevated)', borderColor: 'var(--lab-border)', color: 'var(--lab-text)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b px-5 py-4" style={{ background: 'var(--lab-surface)', borderColor: 'var(--lab-border)' }}>
          <div>
            <div className="text-xs uppercase tracking-wider" style={{ color: 'var(--lab-muted)' }}>
              Dettaglio partita
            </div>
            <div className="text-lg font-semibold">
              {detail ? `${detail.home_team} — ${detail.away_team}` : `#${matchId}`}
            </div>
          </div>
          <button type="button" className="lab-btn-ghost" onClick={onClose}>
            Chiudi
          </button>
        </div>

        <div className="space-y-5 p-5">
          {loading && <p style={{ color: 'var(--lab-muted)' }}>Caricamento…</p>}
          {detail && (
            <>
              <section>
                <h3 className="mb-2 text-sm font-semibold" style={{ color: 'var(--lab-cyan)' }}>
                  Risultato
                </h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>FT: {detail.ft_home_goals ?? '—'}–{detail.ft_away_goals ?? '—'} ({detail.ft_result ?? '—'})</div>
                  <div>HT: {detail.ht_home_goals ?? '—'}–{detail.ht_away_goals ?? '—'} ({detail.ht_result ?? '—'})</div>
                  <div>Data: {detail.match_date ?? '—'}</div>
                  <div>Arbitro: {detail.referee ?? '—'}</div>
                  <div>
                    Qualità:{' '}
                    <span className={`rounded px-2 text-xs lab-badge-${detail.row_quality_status === 'complete' ? 'ok' : detail.row_quality_status === 'error' ? 'err' : 'warn'}`}>
                      {qualityLabel(detail.row_quality_status)}
                    </span>
                  </div>
                </div>
              </section>

              <section>
                <h3 className="mb-2 text-sm font-semibold" style={{ color: 'var(--lab-cyan)' }}>
                  Statistiche
                </h3>
                <div className="grid grid-cols-2 gap-2 text-sm tabular-nums">
                  <div>Tiri: {detail.home_shots ?? '—'} / {detail.away_shots ?? '—'}</div>
                  <div>SOT: {detail.home_shots_on_target ?? '—'} / {detail.away_shots_on_target ?? '—'}</div>
                  <div>Falli: {detail.home_fouls ?? '—'} / {detail.away_fouls ?? '—'}</div>
                  <div>Corner: {detail.home_corners ?? '—'} / {detail.away_corners ?? '—'}</div>
                  <div>Gialli: {detail.home_yellow_cards ?? '—'} / {detail.away_yellow_cards ?? '—'}</div>
                  <div>Rossi: {detail.home_red_cards ?? '—'} / {detail.away_red_cards ?? '—'}</div>
                </div>
              </section>

              <section>
                <h3 className="mb-2 text-sm font-semibold" style={{ color: 'var(--lab-cyan)' }}>
                  Quote Bet365
                </h3>
                <div className="overflow-x-auto text-sm">
                  <table className="lab-table">
                    <thead>
                      <tr>
                        <th>Mercato</th>
                        <th>Pre</th>
                        <th>Closing</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(
                        [
                          ['1', 'home'],
                          ['X', 'draw'],
                          ['2', 'away'],
                          ['Over 2.5', 'over_25'],
                          ['Under 2.5', 'under_25'],
                        ] as const
                      ).map(([label, key]) => (
                        <tr key={key}>
                          <td>{label}</td>
                          <td>{formatOdd(detail.odds_movement?.[key]?.pre)}</td>
                          <td>{formatOdd(detail.odds_movement?.[key]?.closing)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
                  AH pre: {formatOdd(detail.asian_handicap_home_line)} · {formatOdd(detail.bet365_ah_home)} /{' '}
                  {formatOdd(detail.bet365_ah_away)}
                </div>
              </section>

              {detail.issues?.length > 0 && (
                <section>
                  <h3 className="mb-2 text-sm font-semibold" style={{ color: 'var(--lab-warn)' }}>
                    Anomalie
                  </h3>
                  <ul className="space-y-1 text-sm">
                    {detail.issues.map((i) => (
                      <li key={i.id}>
                        [{i.severity}] {i.message}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <section>
                <button type="button" className="lab-btn-ghost text-sm" onClick={() => setRawOpen((v) => !v)}>
                  {rawOpen ? 'Nascondi raw source' : 'Mostra raw source'}
                </button>
                {rawOpen && (
                  <pre className="mt-2 max-h-64 overflow-auto rounded-lg p-3 text-xs" style={{ background: 'rgba(0,0,0,0.35)' }}>
                    {JSON.stringify(detail.raw_json, null, 2)}
                  </pre>
                )}
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
