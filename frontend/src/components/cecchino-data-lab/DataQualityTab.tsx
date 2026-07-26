import { useEffect, useState } from 'react'
import { getCecchinoLabIssues, type CecchinoLabIssue } from '../../lib/cecchinoLabApi'

type Props = {
  refreshKey: number
  onOpenMatch: (matchId: number) => void
}

export function DataQualityTab({ refreshKey, onOpenMatch }: Props) {
  const [items, setItems] = useState<CecchinoLabIssue[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [severity, setSeverity] = useState('')
  const [issueCode, setIssueCode] = useState('')
  const [topCodes, setTopCodes] = useState<Array<{ issue_code: string; count: number }>>([])
  const [severityCounts, setSeverityCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    getCecchinoLabIssues({
      severity: severity || undefined,
      issue_code: issueCode || undefined,
      page,
      page_size: 50,
    })
      .then((res) => {
        if (!cancelled) {
          setItems(res.items)
          setTotal(res.total)
          setTopCodes(res.top_issue_codes || [])
          setSeverityCounts(res.severity_counts || {})
        }
      })
      .catch(() => {
        if (!cancelled) {
          setItems([])
          setTotal(0)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey, severity, issueCode, page])

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="lab-card p-4">
          <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>Errori</div>
          <div className="text-2xl font-semibold" style={{ color: 'var(--lab-err)' }}>
            {severityCounts.error ?? 0}
          </div>
        </div>
        <div className="lab-card p-4">
          <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>Warning</div>
          <div className="text-2xl font-semibold" style={{ color: 'var(--lab-warn)' }}>
            {severityCounts.warning ?? 0}
          </div>
        </div>
        <div className="lab-card p-4">
          <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>Info</div>
          <div className="text-2xl font-semibold" style={{ color: 'var(--lab-cyan)' }}>
            {severityCounts.info ?? 0}
          </div>
        </div>
      </div>

      <div className="lab-card p-4">
        <h3 className="mb-2 text-sm font-semibold">Tipologie più frequenti</h3>
        {topCodes.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>Nessuna anomalia.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {topCodes.map((c) => (
              <button
                key={c.issue_code}
                type="button"
                className="rounded-lg px-3 py-1 text-xs lab-badge-muted"
                onClick={() => {
                  setIssueCode(c.issue_code)
                  setPage(1)
                }}
              >
                {c.issue_code} · {c.count}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <select
          className="lab-input max-w-xs"
          value={severity}
          onChange={(e) => {
            setSeverity(e.target.value)
            setPage(1)
          }}
        >
          <option value="">Severità: tutte</option>
          <option value="error">error</option>
          <option value="warning">warning</option>
          <option value="info">info</option>
        </select>
        <input
          className="lab-input max-w-xs"
          placeholder="issue_code"
          value={issueCode}
          onChange={(e) => {
            setIssueCode(e.target.value)
            setPage(1)
          }}
        />
      </div>

      <div className="lab-table-wrap">
        <table className="lab-table">
          <thead>
            <tr>
              <th>Severità</th>
              <th>Codice</th>
              <th>Messaggio</th>
              <th>Riga</th>
              <th>Partita</th>
            </tr>
          </thead>
          <tbody>
            {items.map((iss) => (
              <tr key={iss.id}>
                <td>
                  <span
                    className={`rounded px-2 text-xs ${
                      iss.severity === 'error'
                        ? 'lab-badge-err'
                        : iss.severity === 'warning'
                          ? 'lab-badge-warn'
                          : 'lab-badge-muted'
                    }`}
                  >
                    {iss.severity}
                  </span>
                </td>
                <td>{iss.issue_code}</td>
                <td className="max-w-md truncate">{iss.message}</td>
                <td>{iss.source_row_number ?? '—'}</td>
                <td>
                  {iss.match_id != null ? (
                    <button type="button" className="lab-btn-ghost px-2 py-0.5 text-xs" onClick={() => onOpenMatch(iss.match_id!)}>
                      #{iss.match_id}
                    </button>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-center" style={{ color: 'var(--lab-muted)' }}>
                  Nessuna anomalia.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="text-sm" style={{ color: 'var(--lab-muted)' }}>
        Totale filtrato: {total} · pagina {page}
        <button type="button" className="lab-btn-ghost ml-2" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          ←
        </button>
        <button type="button" className="lab-btn-ghost ml-1" onClick={() => setPage((p) => p + 1)}>
          →
        </button>
      </div>
    </div>
  )
}
