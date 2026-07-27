import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  downloadCecchinoLabQualityExport,
  getCecchinoLabDatasets,
  getCecchinoLabIssues,
  type CecchinoLabDataset,
  type CecchinoLabIssue,
} from '../../lib/cecchinoLabApi'

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
  const [datasetId, setDatasetId] = useState('')
  const [season, setSeason] = useState('')
  const [competition, setCompetition] = useState('')
  const [datasets, setDatasets] = useState<CecchinoLabDataset[]>([])
  const [topCodes, setTopCodes] = useState<Array<{ issue_code: string; count: number }>>([])
  const [severityCounts, setSeverityCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getCecchinoLabDatasets()
      .then((res) => setDatasets(res.items || []))
      .catch(() => setDatasets([]))
  }, [refreshKey])

  const seasons = Array.from(new Set(datasets.map((d) => d.season_label))).sort().reverse()
  const competitions = Array.from(new Set(datasets.map((d) => d.competition_name))).sort()

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getCecchinoLabIssues({
      severity: severity || undefined,
      issue_code: issueCode || undefined,
      dataset_id: datasetId ? Number(datasetId) : undefined,
      season_label: season || undefined,
      competition: competition || undefined,
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
  }, [refreshKey, severity, issueCode, datasetId, season, competition, page])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setExportOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const runExport = async (format: 'csv' | 'json', scope: 'filtered' | 'all') => {
    setExportOpen(false)
    setExporting(true)
    try {
      await downloadCecchinoLabQualityExport({
        format,
        scope,
        severity: severity || undefined,
        issue_code: issueCode || undefined,
        dataset_id: datasetId ? Number(datasetId) : undefined,
        competition: competition || undefined,
        season_label: season || undefined,
      })
      toast.success(`Export ${format.toUpperCase()} completato`)
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Export fallito')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid flex-1 gap-3 sm:grid-cols-3">
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

        <div className="flex flex-col items-end gap-1" ref={menuRef}>
          <div className="relative">
            <button
              type="button"
              className="lab-btn"
              disabled={exporting}
              onClick={() => setExportOpen((v) => !v)}
              style={{
                background: 'linear-gradient(135deg, rgba(46,230,255,0.2), rgba(61,214,140,0.12))',
                border: '1px solid var(--lab-cyan)',
              }}
            >
              {exporting ? 'Esportazione…' : 'Esporta segnalazioni'}
            </button>
            {exportOpen ? (
              <div
                className="absolute right-0 z-40 mt-2 min-w-[220px] overflow-hidden rounded-xl shadow-xl"
                style={{ background: '#0f1c2c', border: '1px solid var(--lab-border)' }}
              >
                {(
                  [
                    ['csv', 'filtered', 'CSV — filtri attivi'],
                    ['json', 'filtered', 'JSON — filtri attivi'],
                    ['csv', 'all', 'CSV — tutte'],
                    ['json', 'all', 'JSON — tutte'],
                  ] as const
                ).map(([fmt, scope, label]) => (
                  <button
                    key={`${fmt}-${scope}`}
                    type="button"
                    className="block w-full px-4 py-2.5 text-left text-sm hover:bg-white/5"
                    onClick={() => void runExport(fmt, scope)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className="text-xs tabular-nums" style={{ color: 'var(--lab-muted)' }}>
            {total.toLocaleString('it-IT')} segnalazioni nel filtro corrente
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
        <select
          className="lab-input max-w-xs"
          value={datasetId}
          onChange={(e) => {
            setDatasetId(e.target.value)
            setPage(1)
          }}
        >
          <option value="">Dataset: tutti</option>
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.competition_name} · {d.season_label}
            </option>
          ))}
        </select>
        <select
          className="lab-input max-w-xs"
          value={season}
          onChange={(e) => {
            setSeason(e.target.value)
            setPage(1)
          }}
        >
          <option value="">Stagione: tutte</option>
          {seasons.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          className="lab-input max-w-xs"
          value={competition}
          onChange={(e) => {
            setCompetition(e.target.value)
            setPage(1)
          }}
        >
          <option value="">Campionato: tutti</option>
          {competitions.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
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
            {loading ? (
              <tr>
                <td colSpan={5} className="py-8 text-center" style={{ color: 'var(--lab-muted)' }}>
                  Caricamento…
                </td>
              </tr>
            ) : null}
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
