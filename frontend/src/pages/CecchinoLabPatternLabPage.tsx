import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { CecchinoLabShell } from '../components/cecchino-data-lab/CecchinoLabShell'
import {
  downloadPatternLabDiscoveryExport,
  fetchPatternLabBetBuilderReplay,
  formatNum,
  formatPct,
  listPatternLabRuns,
  queryPatternLab,
  type PatternLabBetBuilderReplayResponse,
  type PatternLabFilters,
  type PatternLabQueryResponse,
  type PatternLabRunItem,
} from '../lib/patternLabApi'

type TabId = 'explore' | 'bet_builder'

function parseRunIds(raw: string | null): number[] {
  if (!raw) return []
  return raw
    .split(',')
    .map((x) => Number(x.trim()))
    .filter((n) => Number.isFinite(n) && n > 0)
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="lab-card rounded-lg p-3">
      <div className="text-[11px] uppercase tracking-wide" style={{ color: 'var(--lab-muted)' }}>
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
    </div>
  )
}

export function CecchinoLabPatternLabPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [runs, setRuns] = useState<PatternLabRunItem[]>([])
  const [includePilots, setIncludePilots] = useState(false)
  const [selectedRunIds, setSelectedRunIds] = useState<number[]>(() =>
    parseRunIds(searchParams.get('run_ids')),
  )
  const [tab, setTab] = useState<TabId>('explore')
  const [loading, setLoading] = useState(false)
  const [exportBusy, setExportBusy] = useState(false)
  const [result, setResult] = useState<PatternLabQueryResponse | null>(null)
  const [bbResult, setBbResult] = useState<PatternLabBetBuilderReplayResponse | null>(null)

  // Filters
  const [competition, setCompetition] = useState('')
  const [marketKey, setMarketKey] = useState('')
  const [ratingMin, setRatingMin] = useState('')
  const [ratingMax, setRatingMax] = useState('')
  const [quoteMin, setQuoteMin] = useState('')
  const [quoteMax, setQuoteMax] = useState('')
  const [edgeMin, setEdgeMin] = useState('')
  const [valueOnly, setValueOnly] = useState(false)
  const [signalsMin, setSignalsMin] = useState('')
  const [geometryMin, setGeometryMin] = useState('')
  const [purchMin, setPurchMin] = useState('')
  const [goalMin, setGoalMin] = useState('')
  const [bbActive, setBbActive] = useState(false)
  const [outcome, setOutcome] = useState('')
  const [quoteType, setQuoteType] = useState('')

  const filters: PatternLabFilters = useMemo(() => {
    const f: PatternLabFilters = { eligibility: 'eligible_core' }
    if (competition.trim()) f.competitions = [competition.trim()]
    if (marketKey.trim()) f.market_keys = [marketKey.trim()]
    if (ratingMin !== '') f.rating_min = Number(ratingMin)
    if (ratingMax !== '') f.rating_max = Number(ratingMax)
    if (quoteMin !== '') f.quote_min = Number(quoteMin)
    if (quoteMax !== '') f.quote_max = Number(quoteMax)
    if (edgeMin !== '') f.edge_min = Number(edgeMin)
    if (valueOnly) f.value = true
    if (signalsMin !== '') f.signals_count_min = Number(signalsMin)
    if (geometryMin !== '') f.gap_coherence_score_min = Number(geometryMin)
    if (purchMin !== '') f.purchasability_v36_min = Number(purchMin)
    if (goalMin !== '') f.goal_composite_min = Number(goalMin)
    if (bbActive) f.bet_builder_active = true
    if (outcome) f.outcome = outcome
    if (quoteType) f.quote_type = quoteType
    return f
  }, [
    competition,
    marketKey,
    ratingMin,
    ratingMax,
    quoteMin,
    quoteMax,
    edgeMin,
    valueOnly,
    signalsMin,
    geometryMin,
    purchMin,
    goalMin,
    bbActive,
    outcome,
    quoteType,
  ])

  const loadRuns = useCallback(async () => {
    try {
      const res = await listPatternLabRuns({ include_pilots: includePilots })
      setRuns(res.items)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Errore caricamento run')
    }
  }, [includePilots])

  useEffect(() => {
    void loadRuns()
  }, [loadRuns])

  useEffect(() => {
    const fromUrl = parseRunIds(searchParams.get('run_ids'))
    if (fromUrl.length && fromUrl.join(',') !== selectedRunIds.join(',')) {
      setSelectedRunIds(fromUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  const syncUrl = (ids: number[]) => {
    const next = new URLSearchParams(searchParams)
    if (ids.length) next.set('run_ids', ids.join(','))
    else next.delete('run_ids')
    setSearchParams(next, { replace: true })
  }

  const toggleRun = (runId: number) => {
    setSelectedRunIds((prev) => {
      const next = prev.includes(runId) ? prev.filter((x) => x !== runId) : [...prev, runId]
      syncUrl(next)
      return next
    })
  }

  const selectAllFull = () => {
    const ids = runs.filter((r) => !r.is_pilot).map((r) => r.run_id)
    setSelectedRunIds(ids)
    syncUrl(ids)
  }

  const runQuery = async () => {
    if (!selectedRunIds.length) {
      toast.error('Seleziona almeno una run')
      return
    }
    setLoading(true)
    try {
      if (tab === 'bet_builder') {
        const res = await fetchPatternLabBetBuilderReplay({
          run_ids: selectedRunIds,
          filters,
        })
        setBbResult(res)
      } else {
        const res = await queryPatternLab({
          run_ids: selectedRunIds,
          filters,
          include_rows: true,
          page: 1,
          page_size: 80,
        })
        setResult(res)
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Errore query Pattern Lab')
    } finally {
      setLoading(false)
    }
  }

  const onExport = async (mode: 'full_selected_runs' | 'current_filters') => {
    if (!selectedRunIds.length) {
      toast.error('Seleziona almeno una run')
      return
    }
    setExportBusy(true)
    try {
      const blob = await downloadPatternLabDiscoveryExport({
        run_ids: selectedRunIds,
        mode,
        filters: mode === 'current_filters' ? filters : { eligibility: 'eligible_core' },
        include_observational_only: true,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `pattern_lab_discovery_${selectedRunIds.join('-')}.zip`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Export Pattern Discovery avviato')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export fallito')
    } finally {
      setExportBusy(false)
    }
  }

  const summary = tab === 'bet_builder' ? bbResult?.summary : result?.summary
  const breakdown = tab === 'bet_builder' ? bbResult?.breakdown : result?.breakdown

  return (
    <CecchinoLabShell>
      <div className="space-y-4 p-4 sm:p-6">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--lab-cyan)' }}>
              Pattern Lab
            </div>
            <h1 className="mt-1 text-2xl font-semibold">Analisi multi-run MATCH+MARKET</h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--lab-muted)' }}>
              Layer READ-ONLY su snapshot V4. Goal Intensity etichettato V4-compat. Acquistabilità solo V3.6.
            </p>
            <Link to="/cecchino-lab" className="mt-2 inline-block text-sm underline" style={{ color: 'var(--lab-cyan)' }}>
              ← Cecchino Lab
            </Link>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="lab-btn rounded-md px-3 py-2 text-sm"
              disabled={exportBusy}
              onClick={() => void onExport('full_selected_runs')}
            >
              Esporta dataset Pattern Discovery
            </button>
            <button
              type="button"
              className="rounded-md border px-3 py-2 text-sm"
              style={{ borderColor: 'var(--lab-border)' }}
              disabled={exportBusy}
              onClick={() => void onExport('current_filters')}
            >
              Export solo filtri correnti
            </button>
          </div>
        </header>

        <section className="lab-card rounded-xl p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Run / Stagioni</h2>
            <div className="flex items-center gap-3 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={includePilots}
                  onChange={(e) => setIncludePilots(e.target.checked)}
                />
                Mostra pilot (tech)
              </label>
              <button type="button" className="underline" onClick={selectAllFull}>
                Seleziona tutte full
              </button>
            </div>
          </div>
          <div className="mt-3 grid max-h-48 gap-2 overflow-auto sm:grid-cols-2 lg:grid-cols-3">
            {runs.map((r) => (
              <label
                key={r.run_id}
                className="flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm"
                style={{ borderColor: 'var(--lab-border)' }}
              >
                <input
                  type="checkbox"
                  checked={selectedRunIds.includes(r.run_id)}
                  onChange={() => toggleRun(r.run_id)}
                />
                <span>
                  <span className="font-medium">#{r.run_id}</span> · {r.season_label}
                  <span className="mt-0.5 block text-[11px]" style={{ color: 'var(--lab-muted)' }}>
                    {r.run_scope}
                    {r.is_pilot ? ' · pilot' : ''} · eleggibili {r.matches_eligible_core ?? '—'}
                  </span>
                </span>
              </label>
            ))}
            {!runs.length && (
              <div className="text-sm" style={{ color: 'var(--lab-muted)' }}>
                Nessuna run completata disponibile.
              </div>
            )}
          </div>
        </section>

        <section className="lab-card rounded-xl p-4">
          <h2 className="font-semibold">Filtri (combinabili, nessun gate obbligatorio)</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-sm">
              Campionato
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={competition} onChange={(e) => setCompetition(e.target.value)} placeholder="Serie A" />
            </label>
            <label className="text-sm">
              Mercato
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={marketKey} onChange={(e) => setMarketKey(e.target.value)} placeholder="HOME" />
            </label>
            <label className="text-sm">
              Rating min
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={ratingMin} onChange={(e) => setRatingMin(e.target.value)} />
            </label>
            <label className="text-sm">
              Rating max
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={ratingMax} onChange={(e) => setRatingMax(e.target.value)} />
            </label>
            <label className="text-sm">
              Quota min
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={quoteMin} onChange={(e) => setQuoteMin(e.target.value)} />
            </label>
            <label className="text-sm">
              Quota max
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={quoteMax} onChange={(e) => setQuoteMax(e.target.value)} />
            </label>
            <label className="text-sm">
              Edge min
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={edgeMin} onChange={(e) => setEdgeMin(e.target.value)} />
            </label>
            <label className="text-sm">
              Signals min
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={signalsMin} onChange={(e) => setSignalsMin(e.target.value)} />
            </label>
            <label className="text-sm">
              Geometry min
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={geometryMin} onChange={(e) => setGeometryMin(e.target.value)} />
            </label>
            <label className="text-sm">
              Acq V3.6 min
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={purchMin} onChange={(e) => setPurchMin(e.target.value)} />
            </label>
            <label className="text-sm">
              Goal V4-compat min
              <input className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={goalMin} onChange={(e) => setGoalMin(e.target.value)} />
            </label>
            <label className="text-sm">
              Esito
              <select className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
                <option value="">Tutti</option>
                <option value="won">Won</option>
                <option value="lost">Lost</option>
                <option value="void">Void</option>
              </select>
            </label>
            <label className="text-sm">
              Quote type
              <select className="mt-1 w-full rounded border bg-transparent px-2 py-1.5" value={quoteType} onChange={(e) => setQuoteType(e.target.value)}>
                <option value="">Tutti</option>
                <option value="real">Real</option>
                <option value="derived">Derived</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm pt-6">
              <input type="checkbox" checked={valueOnly} onChange={(e) => setValueOnly(e.target.checked)} />
              Value positivo
            </label>
            <label className="flex items-center gap-2 text-sm pt-6">
              <input type="checkbox" checked={bbActive} onChange={(e) => setBbActive(e.target.checked)} />
              Bet Builder active
            </label>
          </div>
          <div className="mt-4 flex gap-2">
            <button type="button" className="lab-btn rounded-md px-4 py-2 text-sm" disabled={loading} onClick={() => void runQuery()}>
              {loading ? 'Calcolo…' : 'Applica filtri'}
            </button>
          </div>
        </section>

        {summary && (
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
            <MetricCard label="Selections" value={String(summary.selections)} />
            <MetricCard label="Wins" value={String(summary.wins)} />
            <MetricCard label="Losses" value={String(summary.losses)} />
            <MetricCard label="Void" value={String(summary.void)} />
            <MetricCard label="Win rate" value={formatPct(summary.win_rate)} />
            <MetricCard label="Quota media" value={formatNum(summary.avg_quota)} />
            <MetricCard label="Profit 1u" value={formatNum(summary.profit_1u)} />
            <MetricCard label="ROI" value={formatPct(summary.roi)} />
          </section>
        )}

        {breakdown && (
          <section className="grid gap-4 lg:grid-cols-3">
            {(
              [
                ['Per stagione', breakdown.by_season],
                ['Per campionato', breakdown.by_competition],
                ['Per mercato', breakdown.by_market],
              ] as const
            ).map(([title, rows]) => (
              <div key={title} className="lab-card rounded-xl p-4">
                <h3 className="font-semibold">{title}</h3>
                <div className="mt-2 max-h-56 overflow-auto text-sm">
                  <table className="lab-table w-full">
                    <thead>
                      <tr>
                        <th>Key</th>
                        <th>N</th>
                        <th>WR</th>
                        <th>ROI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.slice(0, 40).map((r) => (
                        <tr key={r.key}>
                          <td>{r.key}</td>
                          <td>{r.selections}</td>
                          <td>{formatPct(r.win_rate)}</td>
                          <td>{formatPct(r.roi)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </section>
        )}

        <section className="lab-card rounded-xl p-4">
          <div className="flex gap-3 text-sm">
            <button
              type="button"
              className={tab === 'explore' ? 'font-semibold underline' : ''}
              onClick={() => setTab('explore')}
            >
              Esplora righe
            </button>
            <button
              type="button"
              className={tab === 'bet_builder' ? 'font-semibold underline' : ''}
              onClick={() => setTab('bet_builder')}
            >
              Replay Bet Builder
            </button>
          </div>

          {tab === 'explore' && result?.rows?.length ? (
            <div className="mt-3 overflow-auto">
              <table className="lab-table w-full text-xs">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Kickoff</th>
                    <th>Match</th>
                    <th>Market</th>
                    <th>Quota</th>
                    <th>Rating</th>
                    <th>Signals</th>
                    <th>V3.6</th>
                    <th>Geom</th>
                    <th>Goal</th>
                    <th>Esito</th>
                    <th>P/L</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((r) => (
                    <tr key={`${r.run_id}-${r.snapshot_id}-${r.market_key}`}>
                      <td>{String(r.run_id)}</td>
                      <td>{String(r.kickoff_at ?? '').slice(0, 16)}</td>
                      <td>
                        {String(r.home_team)}–{String(r.away_team)}
                      </td>
                      <td>{String(r.market_key)}</td>
                      <td>{formatNum(r.pre_quota_bet365 as number | null)}</td>
                      <td>{String(r.pre_rating ?? '—')}</td>
                      <td>{String(r.pre_signal_count ?? 0)}</td>
                      <td>{formatNum(r.pre_purch_v36_score as number | null, 1)}</td>
                      <td>{formatNum(r.pre_balance_geometry as number | null, 1)}</td>
                      <td>{formatNum(r.pre_goal_v4_compat_composite as number | null, 1)}</td>
                      <td>
                        {r.target_won === true ? 'W' : r.target_lost === true ? 'L' : r.target_void ? 'V' : '—'}
                      </td>
                      <td>{formatNum(r.target_profit_1u as number | null)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {tab === 'bet_builder' && bbResult?.timeline_by_day?.length ? (
            <div className="mt-3 overflow-auto">
              <p className="mb-2 text-xs" style={{ color: 'var(--lab-muted)' }}>
                Sort policy storica: V3.6 al posto di V3.1 Evidence Sort.
              </p>
              <table className="lab-table w-full text-sm">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>N</th>
                    <th>W</th>
                    <th>L</th>
                    <th>Profit</th>
                    <th>ROI</th>
                  </tr>
                </thead>
                <tbody>
                  {bbResult.timeline_by_day.map((d) => (
                    <tr key={d.date}>
                      <td>{d.date}</td>
                      <td>{d.selections}</td>
                      <td>{d.wins}</td>
                      <td>{d.losses}</td>
                      <td>{formatNum(d.profit_1u)}</td>
                      <td>{formatPct(d.roi)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </div>
    </CecchinoLabShell>
  )
}
