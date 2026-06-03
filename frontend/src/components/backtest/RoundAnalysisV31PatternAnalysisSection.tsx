import { useCallback, useState } from 'react'
import {
  getV31PatternAnalysis,
  getV31PatternAnalysisReportJson,
  type V31PatternAnalysis,
  type V31PatternRecommendation,
  type V31PatternStrategyBlock,
  type V31Top3FixtureComparison,
} from '../../lib/api'

const TABS = [
  { id: 'wins', label: 'Pattern vincenti' },
  { id: 'losses', label: 'Partite perse' },
  { id: 'high', label: 'Partite alte e outlier' },
  { id: 'top3', label: 'Confronto top 3' },
  { id: 'recs', label: 'Raccomandazioni' },
] as const

type TabId = (typeof TABS)[number]['id']

type Props = {
  competitionId: number | null
  seasonYear: number
}

function fmtNum(v: number | null | undefined, d = 2): string {
  if (v == null) return '—'
  return v.toFixed(d)
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v.toFixed(1)}%`
}

const WIN_LABELS: Record<string, string> = {
  HEALTHY_WIN: 'Vittorie sane',
  ACCEPTABLE_WIN: 'Vittorie accettabili',
  UNDERSTATED_WIN: 'Vittorie con sottostima',
  EXTREME_WIN_OUTLIER: 'Vittorie outlier estreme',
}

const LOSS_LABELS: Record<string, string> = {
  CLOSE_LOSS: 'Perse di poco',
  NORMAL_LOSS: 'Perse normali',
  BAD_LOSS_OVERESTIMATION: 'Perse per sovrastima',
}

const REC_TYPE_LABEL: Record<string, string> = {
  structural: 'Problema strutturale',
  outlier: 'Evento outlier',
  useful_pattern: 'Pattern utile',
  dangerous_pattern: 'Pattern pericoloso',
}

export function RoundAnalysisV31PatternAnalysisSection({ competitionId, seasonYear }: Props) {
  const [data, setData] = useState<V31PatternAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabId>('wins')
  const [selectedKey, setSelectedKey] = useState<string>('v31_bias_corrected')
  const [clusterFilter, setClusterFilter] = useState<string>('all')

  const run = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    setError(null)
    try {
      const res = await getV31PatternAnalysis(competitionId, seasonYear, { includeFixtures: true })
      setData(res)
      if (res.strategies.length) setSelectedKey(res.strategies[0].key)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore Pattern Analysis')
    } finally {
      setLoading(false)
    }
  }, [competitionId, seasonYear])

  const downloadJson = useCallback(async () => {
    if (competitionId == null) return
    setExporting(true)
    try {
      const payload = await getV31PatternAnalysisReportJson(competitionId, seasonYear)
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `v31-pattern-analysis-${competitionId}-${seasonYear}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export fallito')
    } finally {
      setExporting(false)
    }
  }, [competitionId, seasonYear])

  const selected = data?.strategies.find((s) => s.key === selectedKey) ?? data?.strategies[0]
  const dist = data?.summary.actual_sot_distribution
  const thresholds = data?.summary.dynamic_bucket_thresholds

  const kpiFromStrategy = (s: V31PatternStrategyBlock | undefined) => {
    const wq = s?.win_quality_summary?.counts ?? {}
    const healthy = (wq.HEALTHY_WIN ?? 0) + (wq.ACCEPTABLE_WIN ?? 0)
    const understated = wq.UNDERSTATED_WIN ?? 0
    const badLoss = s?.loss_quality_summary?.counts?.BAD_LOSS_OVERESTIMATION ?? 0
    const extreme = (wq.EXTREME_WIN_OUTLIER ?? 0) + (s?.extreme_outlier_summary?.extreme_actual_count as number ?? 0)
    return { healthy, understated, badLoss, extreme }
  }

  const kpis = kpiFromStrategy(selected)

  return (
    <section className="space-y-4 rounded-lg border border-amber-200 bg-amber-50/30 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Pattern Analysis v3.1</h2>
          <p className="mt-1 max-w-3xl text-xs text-slate-600">
            Coverage WIN non significa sempre previsione corretta. Una partita può essere vinta perché il
            reale supera il predetto, ma se il distacco è molto alto il modello potrebbe avere sottostimato.
            Gli eventi estremi vengono separati per evitare di calibrare il modello su anomalie rare.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={loading || competitionId == null}
            className="rounded-lg border border-amber-700 bg-amber-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50"
            onClick={() => void run()}
          >
            {loading ? 'Analisi…' : 'Esegui Pattern Analysis'}
          </button>
          <button
            type="button"
            disabled={exporting || !data}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => void downloadJson()}
          >
            {exporting ? 'Export…' : 'Scarica report JSON'}
          </button>
        </div>
      </div>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      {data ? (
        <>
          {dist ? (
            <p className="text-xs text-slate-600">
              Distribuzione actual: media {fmtNum(dist.mean)} · mediana {fmtNum(dist.median)} · p75{' '}
              {fmtNum(thresholds?.p75)} · p90 {fmtNum(thresholds?.p90)} · p95 {fmtNum(thresholds?.p95)} ·
              max {fmtNum(dist.max)} ({dist.count} partite)
            </p>
          ) : null}

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <KpiBox title="Vittorie sane" value={String(kpis.healthy)} tone="emerald" />
            <KpiBox title="Vittorie con sottostima" value={String(kpis.understated)} tone="amber" />
            <KpiBox title="Perse per sovrastima" value={String(kpis.badLoss)} tone="rose" />
            <KpiBox title="Eventi estremi" value={String(kpis.extreme)} tone="violet" />
          </div>

          <div className="flex flex-wrap gap-2">
            {data.strategies.map((s) => (
              <button
                key={s.key}
                type="button"
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  selectedKey === s.key
                    ? 'bg-amber-800 text-white'
                    : 'border border-slate-300 bg-white text-slate-700'
                }`}
                onClick={() => setSelectedKey(s.key)}
              >
                {s.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap gap-1 border-b border-slate-200 pb-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`rounded-t px-3 py-1.5 text-xs font-medium ${
                  tab === t.id ? 'bg-white text-amber-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                }`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {selected ? (
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              {tab === 'wins' ? <WinningPanel strategy={selected} /> : null}
              {tab === 'losses' ? <LosingPanel strategy={selected} /> : null}
              {tab === 'high' ? <HighOutlierPanel strategy={selected} dist={dist} thresholds={thresholds} /> : null}
              {tab === 'top3' ? (
                <Top3Panel
                  fixtures={data.top3_fixtures ?? []}
                  clusterSummary={data.summary.top3_cluster_summary}
                  clusterFilter={clusterFilter}
                  onClusterFilter={setClusterFilter}
                />
              ) : null}
              {tab === 'recs' ? <RecommendationsPanel recs={data.summary.recommendations ?? []} /> : null}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  )
}

function KpiBox({
  title,
  value,
  tone,
}: {
  title: string
  value: string
  tone: 'emerald' | 'amber' | 'rose' | 'violet'
}) {
  const colors = {
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    amber: 'border-amber-200 bg-amber-50 text-amber-900',
    rose: 'border-rose-200 bg-rose-50 text-rose-900',
    violet: 'border-violet-200 bg-violet-50 text-violet-900',
  }
  return (
    <div className={`rounded-lg border p-3 text-xs ${colors[tone]}`}>
      <p className="font-medium opacity-80">{title}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  )
}

function CategoryTable({
  categories,
  labels,
}: {
  categories: Record<string, { count: number; pct_of_total: number; avg_abs_error?: number | null; examples?: Array<Record<string, unknown>> }>
  labels: Record<string, string>
}) {
  return (
    <div className="space-y-4">
      {Object.entries(labels).map(([key, label]) => {
        const cat = categories[key]
        if (!cat) return null
        return (
          <div key={key} className="rounded border border-slate-100 p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h4 className="font-medium text-slate-900">{label}</h4>
              <span className="text-xs text-slate-600">
                {cat.count} partite · {fmtPct(cat.pct_of_total)} · MAE {fmtNum(cat.avg_abs_error)}
              </span>
            </div>
            {cat.examples?.length ? (
              <ul className="mt-2 space-y-1 text-xs text-slate-700">
                {cat.examples.slice(0, 3).map((ex) => (
                  <li key={String(ex.fixture_id)}>
                    {String(ex.match ?? ex.fixture_id)} — pred {fmtNum(ex.predicted_total_sot as number)} / actual{' '}
                    {fmtNum(ex.actual_total_sot as number)} ({String(ex.win_quality ?? '')})
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function WinningPanel({ strategy }: { strategy: V31PatternStrategyBlock }) {
  const wp = strategy.winning_patterns
  if (!wp) return <p className="text-sm text-slate-500">Nessun dato.</p>
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-700">{wp.interpretation}</p>
      <p className="text-xs text-slate-500">
        Vittorie totali: {wp.total_wins} su {wp.total_fixtures} fixture
      </p>
      <CategoryTable categories={wp.categories} labels={WIN_LABELS} />
    </div>
  )
}

function LosingPanel({ strategy }: { strategy: V31PatternStrategyBlock }) {
  const lp = strategy.losing_patterns
  if (!lp) return <p className="text-sm text-slate-500">Nessun dato.</p>
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-700">{lp.interpretation}</p>
      <CategoryTable categories={lp.categories} labels={LOSS_LABELS} />
      {lp.special_categories ? (
        <div className="mt-4 space-y-2">
          <h4 className="text-sm font-medium text-slate-800">Sotto-categorie</h4>
          {Object.entries(lp.special_categories).map(([k, v]) => (
            <p key={k} className="text-xs text-slate-600">
              {k}: {v.count} ({fmtPct(v.pct_of_total)})
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function HighOutlierPanel({
  strategy,
  dist,
  thresholds,
}: {
  strategy: V31PatternStrategyBlock
  dist?: V31PatternAnalysis['summary']['actual_sot_distribution']
  thresholds?: V31PatternAnalysis['summary']['dynamic_bucket_thresholds']
}) {
  const h = strategy.high_and_outlier as Record<string, unknown> | undefined
  const e = strategy.extreme_outlier_summary as Record<string, unknown> | undefined
  if (!h) return <p className="text-sm text-slate-500">Nessun dato.</p>
  return (
    <div className="space-y-3 text-sm text-slate-700">
      <p>{String(h.interpretation ?? '')}</p>
      <ul className="grid gap-1 text-xs sm:grid-cols-2">
        <li>Actual &gt; p75 ({fmtNum(thresholds?.p75)}): {String(h.actual_above_p75)}</li>
        <li>Actual &gt; p90 ({fmtNum(thresholds?.p90)}): {String(h.actual_above_p90)}</li>
        <li>Actual &gt; p95 ({fmtNum(thresholds?.p95)}): {String(h.actual_above_p95)}</li>
        <li>Actual statico ≥15: {String(h.actual_static_extreme_gte_15)}</li>
        <li>Pred high: {String(h.predicted_high)} · missed high: {String(h.missed_high)}</li>
        <li>Missed extreme: {String(h.missed_extreme)}</li>
      </ul>
      {e ? (
        <p className="text-xs text-violet-800">
          Outlier estremi: {String(e.extreme_actual_count)} actual · {String(e.extreme_win_outlier_count)} vittorie
          outlier · peso calibrazione ridotto su {String(h.calibration_weight_reduced_count)} casi
        </p>
      ) : null}
      {dist ? <p className="text-[10px] text-slate-500">Media campionato actual: {fmtNum(dist.mean)} SOT</p> : null}
    </div>
  )
}

function Top3Panel({
  fixtures,
  clusterSummary,
  clusterFilter,
  onClusterFilter,
}: {
  fixtures: V31Top3FixtureComparison[]
  clusterSummary?: { counts?: Record<string, number>; pct?: Record<string, number> }
  clusterFilter: string
  onClusterFilter: (v: string) => void
}) {
  const clusters = Object.keys(clusterSummary?.counts ?? {})
  const filtered =
    clusterFilter === 'all' ? fixtures : fixtures.filter((f) => f.top3_cluster === clusterFilter)

  return (
    <div className="space-y-3">
      {clusters.length ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={`rounded px-2 py-0.5 text-[10px] ${clusterFilter === 'all' ? 'bg-slate-800 text-white' : 'border'}`}
            onClick={() => onClusterFilter('all')}
          >
            Tutti ({fixtures.length})
          </button>
          {clusters.map((c) => (
            <button
              key={c}
              type="button"
              className={`rounded px-2 py-0.5 text-[10px] ${clusterFilter === c ? 'bg-slate-800 text-white' : 'border'}`}
              onClick={() => onClusterFilter(c)}
            >
              {c} ({clusterSummary?.counts?.[c] ?? 0})
            </button>
          ))}
        </div>
      ) : null}
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead>
            <tr className="border-b text-slate-500">
              <th className="py-1 pr-2">Match</th>
              <th className="py-1 pr-2">Actual</th>
              <th className="py-1 pr-2">Bias</th>
              <th className="py-1 pr-2">Hybrid</th>
              <th className="py-1 pr-2">Chaos</th>
              <th className="py-1 pr-2">Cluster</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 40).map((f) => (
              <tr key={f.fixture_id} className="border-b border-slate-50">
                <td className="py-1 pr-2">{f.match ?? f.fixture_id}</td>
                <td className="py-1 pr-2">
                  {f.actual_total_sot} ({f.actual_bucket_dynamic})
                </td>
                <td className="py-1 pr-2">{fmtNum(f.models?.v31_bias_corrected?.predicted_total_sot)}</td>
                <td className="py-1 pr-2">{fmtNum(f.models?.v31_bias_dynamic_high_guard?.predicted_total_sot)}</td>
                <td className="py-1 pr-2">{fmtNum(f.models?.v31_chaos_game?.predicted_total_sot)}</td>
                <td className="py-1 pr-2 text-[10px]">{f.top3_cluster}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RecommendationsPanel({ recs }: { recs: V31PatternRecommendation[] }) {
  if (!recs.length) return <p className="text-sm text-slate-500">Nessuna raccomandazione.</p>
  return (
    <ul className="space-y-3">
      {recs.map((r, i) => (
        <li key={i} className="rounded border border-slate-100 p-3 text-sm">
          <span className="font-medium text-slate-800">{REC_TYPE_LABEL[r.type] ?? r.type}</span>
          <span className="ml-2 text-xs text-slate-500">({r.severity})</span>
          <p className="mt-1 text-slate-700">{r.message}</p>
        </li>
      ))}
    </ul>
  )
}
