import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card } from '../components/ui/Card'
import {
  formatPct,
  getPatternInsightCandidates,
  getPatternInsightSummary,
  type PatternInsightCandidate,
  type PatternInsightSummary,
  type PatternInsightSummaryTarget,
  type PatternInsightTargetType,
} from '../lib/patternInsightsApi'

const PAGE_SIZE = 30
const ROI_COLOR = '#059669'
const DEVIATION_UP_COLOR = '#2563eb'
const DEVIATION_DOWN_COLOR = '#dc2626'
const MARKET_COLOR = '#4f46e5'
const SYNTHETIC_COLOR = '#0891b2'

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
      {hint ? <div className="mt-0.5 text-xs text-slate-400">{hint}</div> : null}
    </div>
  )
}

function TopMarketsChart({ targets }: { targets: PatternInsightSummaryTarget[] }) {
  const data = useMemo(
    () =>
      targets
        .filter((t) => t.target_type === 'market' && t.best_roi_pct != null)
        .sort((a, b) => (b.best_roi_pct ?? 0) - (a.best_roi_pct ?? 0))
        .slice(0, 12)
        .map((t) => ({ name: t.target_label, roi: t.best_roi_pct ?? 0 })),
    [targets],
  )
  if (data.length === 0) return <div className="text-sm text-slate-400">Nessun dato disponibile.</div>
  return (
    <ResponsiveContainer width="100%" height={360}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 40 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" unit="%" tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" width={160} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v) => [`${Number(v).toFixed(1)}%`, 'Miglior ROI']} />
        <Bar dataKey="roi" fill={ROI_COLOR} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function TopSyntheticChart({ targets }: { targets: PatternInsightSummaryTarget[] }) {
  const data = useMemo(
    () =>
      targets
        .filter((t) => t.target_type === 'synthetic' && t.best_abs_deviation_pct != null)
        .sort((a, b) => (b.best_abs_deviation_pct ?? 0) - (a.best_abs_deviation_pct ?? 0))
        .slice(0, 14)
        .map((t) => ({ name: t.target_label, deviation: t.best_abs_deviation_pct ?? 0 })),
    [targets],
  )
  if (data.length === 0) return <div className="text-sm text-slate-400">Nessun dato disponibile.</div>
  return (
    <ResponsiveContainer width="100%" height={420}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 40 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" unit=" pt" tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" width={260} tick={{ fontSize: 11 }} />
        <Tooltip
          formatter={(v) => [`${Number(v).toFixed(1)} punti percentuali`, 'Scarto max dalla base']}
        />
        <Bar dataKey="deviation" fill={DEVIATION_UP_COLOR} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function TotalsPie({ totals }: { totals: { market: number; synthetic: number } }) {
  const data = [
    { name: 'Mercati con quota', value: totals.market, color: MARKET_COLOR },
    { name: 'Bersagli senza quota', value: totals.synthetic, color: SYNTHETIC_COLOR },
  ]
  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={2}>
          {data.map((d) => (
            <Cell key={d.name} fill={d.color} />
          ))}
        </Pie>
        <Legend verticalAlign="bottom" height={36} />
        <Tooltip formatter={(v) => Number(v).toLocaleString('it-IT')} />
      </PieChart>
    </ResponsiveContainer>
  )
}

function CandidateRow({ c }: { c: PatternInsightCandidate }) {
  const isMarket = c.target_type === 'market'
  return (
    <tr className="border-b border-slate-100">
      <td className="whitespace-nowrap py-2 pr-3 text-xs font-semibold text-slate-900">{c.target_label}</td>
      <td className="max-w-[340px] py-2 pr-3 text-xs text-slate-600">
        {c.filters_text_human}
        {c.refined_from_text ? (
          <div className="mt-0.5 text-[10px] text-slate-400">raffinato da un pattern piu&apos; semplice</div>
        ) : null}
      </td>
      <td className="whitespace-nowrap py-2 pr-3 text-xs text-slate-600">
        N {c.n} ({c.wins}V/{c.losses}P)
      </td>
      {isMarket ? (
        <>
          <td className="whitespace-nowrap py-2 pr-3 text-xs font-semibold" style={{ color: ROI_COLOR }}>
            {formatPct(c.roi_pct)}
          </td>
          <td className="whitespace-nowrap py-2 pr-3 text-xs text-slate-600">
            {c.avg_quota != null ? c.avg_quota.toFixed(2) : '—'}
          </td>
        </>
      ) : (
        <>
          <td className="whitespace-nowrap py-2 pr-3 text-xs text-slate-600">
            {c.win_rate_pct != null ? `${c.win_rate_pct.toFixed(1)}%` : '—'}
            <span className="text-slate-400"> (base {c.baseline_win_rate_pct?.toFixed(1)}%)</span>
          </td>
          <td
            className="whitespace-nowrap py-2 pr-3 text-xs font-semibold"
            style={{ color: (c.deviation_pct ?? 0) >= 0 ? DEVIATION_UP_COLOR : DEVIATION_DOWN_COLOR }}
          >
            {formatPct(c.deviation_pct)}
          </td>
        </>
      )}
    </tr>
  )
}

export function PatternInsightsPage() {
  const [summary, setSummary] = useState<PatternInsightSummary | null>(null)
  const [loadingSummary, setLoadingSummary] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [targetTypeFilter, setTargetTypeFilter] = useState<'ALL' | PatternInsightTargetType>('ALL')
  const [minN, setMinN] = useState(50)
  const [sort, setSort] = useState<'best' | 'roi_desc' | 'deviation_desc'>('best')
  const [page, setPage] = useState(0)

  const [candidatesTotal, setCandidatesTotal] = useState(0)
  const [candidateItems, setCandidateItems] = useState<PatternInsightCandidate[]>([])
  const [loadingCandidates, setLoadingCandidates] = useState(false)

  const loadSummary = useCallback(async () => {
    setLoadingSummary(true)
    setError(null)
    try {
      setSummary(await getPatternInsightSummary(minN))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento riepilogo')
    } finally {
      setLoadingSummary(false)
    }
  }, [minN])

  useEffect(() => {
    void loadSummary()
  }, [loadSummary])

  const loadCandidates = useCallback(async () => {
    setLoadingCandidates(true)
    try {
      const page_ = await getPatternInsightCandidates({
        targetType: targetTypeFilter === 'ALL' ? undefined : targetTypeFilter,
        minN,
        sort,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      setCandidatesTotal(page_.total)
      setCandidateItems(page_.items)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento pattern')
    } finally {
      setLoadingCandidates(false)
    }
  }, [targetTypeFilter, minN, sort, page])

  useEffect(() => {
    void loadCandidates()
  }, [loadCandidates])

  useEffect(() => {
    setPage(0)
  }, [targetTypeFilter, minN, sort])

  const run = summary?.run ?? null
  const candidatesTotalCount = run?.summary?.candidates_total ?? 0

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Pattern Insights</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">
          Scoperta cieca su Run V2: vocabolario esteso (tiri, tiri in porta, corner, cartellini, arbitro,
          oltre ai pilastri Goal/Balance gia&apos; noti) su 17 mercati con quota (incluso primo tempo e
          Over/Under 0.5/1.5/3.5) piu&apos; bersagli senza quota storica per capire quali profili di partita
          producono quali situazioni.
        </p>
        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          <strong>Attenzione:</strong> per ora e&apos; disponibile una sola stagione Run V2 (2021/22), quindi
          nessun pattern qui e&apos; stato ancora verificato su una stagione successiva mai vista. Trattali
          come ipotesi da confermare, non come pattern gia&apos; validati — specialmente quelli con N basso e
          quota molto alta.
        </div>
      </header>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      {loadingSummary && !summary && <div className="text-sm text-slate-400">Caricamento…</div>}

      {run && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Pattern trovati" value={candidatesTotalCount.toLocaleString('it-IT')} />
          <StatCard
            label="Mercati con quota"
            value={(run.summary?.candidates_by_type?.market ?? 0).toLocaleString('it-IT')}
            hint="17 mercati, incluso 1T"
          />
          <StatCard
            label="Bersagli senza quota"
            value={(run.summary?.candidates_by_type?.synthetic ?? 0).toLocaleString('it-IT')}
            hint="tiri / corner / cartellini"
          />
          <StatCard
            label="Ultima analisi"
            value={run.completed_at ? new Date(run.completed_at).toLocaleDateString('it-IT') : '—'}
            hint={`stagione Run V2 #${run.run_v2_run_id}`}
          />
        </div>
      )}

      {summary && summary.targets.length > 0 && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Card title="Miglior ROI per mercato" className="xl:col-span-2">
            <p className="mb-2 text-xs text-slate-400">
              Il pattern piu&apos; redditizio trovato per ciascun mercato con quota storica.
            </p>
            <TopMarketsChart targets={summary.targets} />
          </Card>
          <Card title="Composizione">
            <p className="mb-2 text-xs text-slate-400">
              Quanti pattern per tipo di bersaglio.
            </p>
            <TotalsPie totals={summary.totals} />
          </Card>
          <Card title="Situazioni piu' prevedibili (tiri, corner, cartellini)" className="xl:col-span-3">
            <p className="mb-2 text-xs text-slate-400">
              Quanto il profilo della partita sposta la probabilita&apos; rispetto alla media generale —
              piu&apos; la barra e&apos; lunga, piu&apos; quella situazione e&apos; prevedibile in anticipo.
            </p>
            <TopSyntheticChart targets={summary.targets} />
          </Card>
        </div>
      )}

      <Card title="Esplora i pattern">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-500">
            Tipo
            <select
              className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              value={targetTypeFilter}
              onChange={(e) => setTargetTypeFilter(e.target.value as typeof targetTypeFilter)}
            >
              <option value="ALL">Tutti</option>
              <option value="market">Solo mercati (con quota)</option>
              <option value="synthetic">Solo tiri/corner/cartellini (senza quota)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-500">
            Campione minimo (N)
            <input
              type="number"
              min={20}
              step={10}
              className="w-24 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              value={minN}
              onChange={(e) => setMinN(Math.max(20, Number(e.target.value) || 20))}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-500">
            Ordina per
            <select
              className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              value={sort}
              onChange={(e) => setSort(e.target.value as typeof sort)}
            >
              <option value="best">Automatico (ROI o scarto)</option>
              <option value="roi_desc">ROI decrescente</option>
              <option value="deviation_desc">Scarto dalla media decrescente</option>
            </select>
          </label>
          <div className="ml-auto text-xs text-slate-400">
            {candidatesTotal.toLocaleString('it-IT')} pattern corrispondenti ai filtri
          </div>
        </div>

        {loadingCandidates && <div className="text-sm text-slate-400">Caricamento…</div>}

        {!loadingCandidates && candidateItems.length === 0 && (
          <div className="text-sm text-slate-400">Nessun pattern corrisponde ai filtri selezionati.</div>
        )}

        {candidateItems.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-3">Bersaglio</th>
                  <th className="py-2 pr-3">Pattern</th>
                  <th className="py-2 pr-3">Campione</th>
                  <th className="py-2 pr-3">ROI / Frequenza</th>
                  <th className="py-2 pr-3">Quota / Scarto</th>
                </tr>
              </thead>
              <tbody>
                {candidateItems.map((c) => (
                  <CandidateRow key={c.id} c={c} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
          <button
            type="button"
            className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            ← Precedenti
          </button>
          <span>
            {candidatesTotal === 0 ? 0 : page * PAGE_SIZE + 1}-
            {Math.min((page + 1) * PAGE_SIZE, candidatesTotal)} di {candidatesTotal.toLocaleString('it-IT')}
          </span>
          <button
            type="button"
            className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40"
            disabled={(page + 1) * PAGE_SIZE >= candidatesTotal}
            onClick={() => setPage((p) => p + 1)}
          >
            Successivi →
          </button>
        </div>
      </Card>
    </div>
  )
}
