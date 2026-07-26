import { useEffect, useState } from 'react'
import { getCecchinoLabDatasets, type CecchinoLabDataset } from '../../lib/cecchinoLabApi'
import { qualityLabel } from './labTheme'

type Props = {
  refreshKey: number
  onOpenMatches: (datasetId: number) => void
}

export function DatasetsTab({ refreshKey, onOpenMatches }: Props) {
  const [items, setItems] = useState<CecchinoLabDataset[]>([])
  const [loading, setLoading] = useState(true)
  const [country, setCountry] = useState('')
  const [competition, setCompetition] = useState('')
  const [season, setSeason] = useState('')
  const [quality, setQuality] = useState('')

  useEffect(() => {
    let cancelled = false
    getCecchinoLabDatasets({
      country: country || undefined,
      competition: competition || undefined,
      season: season || undefined,
      quality_status: quality || undefined,
    })
      .then((res) => {
        if (!cancelled) setItems(res.items)
      })
      .catch(() => {
        if (!cancelled) setItems([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey, country, competition, season, quality])

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <input className="lab-input" placeholder="Paese" value={country} onChange={(e) => setCountry(e.target.value)} />
        <input className="lab-input" placeholder="Campionato" value={competition} onChange={(e) => setCompetition(e.target.value)} />
        <input className="lab-input" placeholder="Stagione" value={season} onChange={(e) => setSeason(e.target.value)} />
        <select className="lab-input" value={quality} onChange={(e) => setQuality(e.target.value)}>
          <option value="">Qualità: tutte</option>
          <option value="complete">complete</option>
          <option value="partial">partial</option>
          <option value="poor">poor</option>
          <option value="unknown">unknown</option>
        </select>
      </div>

      {loading ? (
        <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>Caricamento dataset…</p>
      ) : items.length === 0 ? (
        <div className="lab-card p-10 text-center text-sm" style={{ color: 'var(--lab-muted)' }}>
          Nessun dataset. Importa un CSV per iniziare.
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((d) => (
            <button
              key={d.id}
              type="button"
              className="lab-card p-4 text-left transition hover:ring-1 hover:ring-[var(--lab-cyan)]"
              onClick={() => onOpenMatches(d.id)}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-lg font-semibold">{d.competition_name}</div>
                  <div className="text-sm" style={{ color: 'var(--lab-muted)' }}>
                    {d.country} · {d.season_label}
                    {d.division_code ? ` · ${d.division_code}` : ''}
                  </div>
                </div>
                <span
                  className={`rounded-md px-2 py-0.5 text-xs ${
                    d.data_quality_status === 'complete'
                      ? 'lab-badge-ok'
                      : d.data_quality_status === 'poor'
                        ? 'lab-badge-err'
                        : 'lab-badge-warn'
                  }`}
                >
                  {qualityLabel(d.data_quality_status)}
                </span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
                <div>
                  <div style={{ color: 'var(--lab-muted)' }}>Partite</div>
                  <div className="font-semibold tabular-nums">{d.matches_count}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--lab-muted)' }}>Anomalie</div>
                  <div className="font-semibold tabular-nums">{d.anomalies_count ?? '—'}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--lab-muted)' }}>1X2</div>
                  <div className="tabular-nums">{d.bet365_1x2_coverage_pct ?? '—'}%</div>
                </div>
                <div>
                  <div style={{ color: 'var(--lab-muted)' }}>O/U 2.5</div>
                  <div className="tabular-nums">{d.bet365_ou25_coverage_pct ?? '—'}%</div>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
