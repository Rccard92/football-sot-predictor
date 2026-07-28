import type { HistoricalRunMatchDetail } from '../../../lib/cecchinoLabApi'

type Props = {
  detail: HistoricalRunMatchDetail
  onClose: () => void
}

export function HistoricalRunMatchDetail({ detail, onClose }: Props) {
  const id = detail.identity as Record<string, unknown>
  const pre = detail.prematch
  const res = detail.result_after_lock
  const settlement = (res.settlement as Array<Record<string, unknown>>) || []

  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-4 md:items-center"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-2xl border p-5"
        style={{ background: 'var(--lab-bg-elevated)', borderColor: 'var(--lab-border)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold">
              {String(id.home_team)} vs {String(id.away_team)}
            </h3>
            <p className="text-xs text-[var(--lab-muted)]">
              {String(id.competition)} · {String(id.kickoff_at ?? '—')} · {String(id.eligibility)}
            </p>
          </div>
          <button type="button" className="lab-btn text-xs" onClick={onClose}>
            Chiudi
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div
            className="rounded-xl border p-3"
            style={{ borderColor: 'rgba(46,230,255,0.25)', background: 'rgba(46,230,255,0.05)' }}
          >
            <h4 className="font-medium text-[var(--lab-cyan)]">
              {String(pre.label ?? 'Analisi conosciuta prima della partita')}
            </h4>
            <pre className="mt-2 max-h-64 overflow-auto text-[10px] text-[var(--lab-muted)]">
              {JSON.stringify(
                {
                  cecchino_final: pre.cecchino_final,
                  balance: summarize(pre.balance),
                  goal_intensity: summarize(pre.goal_intensity),
                  purchasability: summarize(pre.purchasability),
                  pre_match_hash: pre.pre_match_hash,
                  locked_at: pre.locked_at,
                },
                null,
                2,
              )}
            </pre>
          </div>
          <div
            className="rounded-xl border p-3"
            style={{ borderColor: 'rgba(61,214,140,0.25)', background: 'rgba(61,214,140,0.05)' }}
          >
            <h4 className="font-medium text-[var(--lab-ok)]">
              {String(res.label ?? 'Risultato collegato dopo il blocco')}
            </h4>
            <pre className="mt-2 max-h-40 overflow-auto text-[10px] text-[var(--lab-muted)]">
              {JSON.stringify({ ft: res.ft, ht: res.ht }, null, 2)}
            </pre>
            <div className="mt-2 lab-table-wrap overflow-x-auto">
              <table className="lab-table w-full text-[10px]">
                <thead>
                  <tr>
                    <th>Mercato</th>
                    <th>Won</th>
                    <th>Quota</th>
                    <th>ROI tipo</th>
                  </tr>
                </thead>
                <tbody>
                  {settlement.map((s) => (
                    <tr key={String(s.market_key)}>
                      <td>{String(s.market_key)}</td>
                      <td>{String(s.won)}</td>
                      <td>{String(s.quota_book ?? '—')}</td>
                      <td>
                        {s.is_real_book_quote
                          ? 'reale'
                          : s.is_derived_quote
                            ? 'derivata'
                            : 'n/d'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function summarize(v: unknown): unknown {
  if (!v || typeof v !== 'object') return v
  const o = v as Record<string, unknown>
  return {
    observation_status: o.observation_status,
    execution_status: o.execution_status,
    keys: Object.keys(o).slice(0, 12),
  }
}
