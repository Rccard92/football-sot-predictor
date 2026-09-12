import { useCallback, useEffect, useState } from 'react'
import { Section } from './PatternInsightsShell'
import {
  getPatternInsightCandidates,
  type PatternInsightCandidate,
  type PatternInsightTargetType,
} from '../../lib/patternInsightsApi'

const PAGE_SIZE = 25

function pct(v: number | null | undefined, d = 1): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(d)}%`
}

function RiskChip({ n }: { n: number }) {
  const label = n < 50 ? 'fragile' : n < 150 ? 'medio' : 'solido'
  const color = n < 50 ? 'var(--pi-neg)' : n < 150 ? 'var(--pi-warn)' : 'var(--pi-pos)'
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
      style={{ color, background: 'rgba(255,255,255,0.04)', border: `1px solid ${color}55` }}
    >
      {label}
    </span>
  )
}

function Row({ c }: { c: PatternInsightCandidate }) {
  const isMarket = c.target_type === 'market'
  return (
    <tr>
      <td className="whitespace-nowrap font-semibold">{c.target_label}</td>
      <td style={{ maxWidth: 420 }}>
        <div className="leading-snug">{c.filters_text_human}</div>
        {c.refined_from_text ? (
          <div className="mt-0.5 text-[10px]" style={{ color: 'var(--pi-muted)' }}>
            raffinamento di un pattern piu&apos; semplice
          </div>
        ) : null}
      </td>
      <td className="whitespace-nowrap tabular-nums">
        <div className="flex items-center gap-2">
          <span>{c.n}</span>
          <RiskChip n={c.n} />
        </div>
        <div className="text-[10px]" style={{ color: 'var(--pi-muted)' }}>
          {c.wins}V · {c.losses}P
        </div>
      </td>
      <td className="whitespace-nowrap tabular-nums">
        {c.win_rate_pct != null ? `${c.win_rate_pct.toFixed(1)}%` : '—'}
        {!isMarket && c.baseline_win_rate_pct != null ? (
          <div className="text-[10px]" style={{ color: 'var(--pi-muted)' }}>
            base {c.baseline_win_rate_pct.toFixed(1)}%
          </div>
        ) : null}
      </td>
      <td className="whitespace-nowrap tabular-nums font-semibold">
        {isMarket ? (
          <span style={{ color: 'var(--pi-pos)' }}>{pct(c.roi_pct)}</span>
        ) : (
          <span
            style={{ color: (c.deviation_pct ?? 0) >= 0 ? 'var(--pi-pos)' : 'var(--pi-neg)' }}
          >
            {pct(c.deviation_pct)}
          </span>
        )}
      </td>
      <td className="whitespace-nowrap tabular-nums">
        {c.avg_quota != null ? c.avg_quota.toFixed(2) : '—'}
      </td>
    </tr>
  )
}

export function PatternExplorer({ defaultMinN = 50 }: { defaultMinN?: number }) {
  const [targetType, setTargetType] = useState<'ALL' | PatternInsightTargetType>('market')
  const [minN, setMinN] = useState(defaultMinN)
  const [sort, setSort] = useState<'best' | 'roi_desc' | 'deviation_desc'>('best')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [items, setItems] = useState<PatternInsightCandidate[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getPatternInsightCandidates({
        targetType: targetType === 'ALL' ? undefined : targetType,
        minN,
        sort,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      setTotal(res.total)
      setItems(res.items)
    } finally {
      setLoading(false)
    }
  }, [targetType, minN, sort, page])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setPage(0)
  }, [targetType, minN, sort])

  return (
    <Section
      title="Esplora i pattern"
      note={`${total.toLocaleString('it-IT')} pattern con i filtri attuali`}
    >
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          Tipo di bersaglio
          <select
            className="pi-select"
            value={targetType}
            onChange={(e) => setTargetType(e.target.value as typeof targetType)}
          >
            <option value="market">Mercati con quota</option>
            <option value="synthetic">Tiri / corner / cartellini</option>
            <option value="ALL">Tutti</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          Campione minimo
          <input
            type="number"
            min={20}
            step={10}
            className="pi-input w-24"
            value={minN}
            onChange={(e) => setMinN(Math.max(20, Number(e.target.value) || 20))}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          Ordinamento
          <select
            className="pi-select"
            value={sort}
            onChange={(e) => setSort(e.target.value as typeof sort)}
          >
            <option value="best">Automatico</option>
            <option value="roi_desc">ROI decrescente</option>
            <option value="deviation_desc">Scarto dalla media</option>
          </select>
        </label>
      </div>

      <div className="pi-scroll" style={{ maxHeight: 560 }}>
        <table className="pi-table">
          <thead>
            <tr>
              <th>Bersaglio</th>
              <th>Pattern</th>
              <th>Campione</th>
              <th>Win rate</th>
              <th>ROI / Scarto</th>
              <th>Quota media</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <Row key={c.id} c={c} />
            ))}
          </tbody>
        </table>
        {loading && (
          <div className="p-3 text-xs" style={{ color: 'var(--pi-muted)' }}>
            Caricamento…
          </div>
        )}
        {!loading && items.length === 0 && (
          <div className="p-3 text-xs" style={{ color: 'var(--pi-muted)' }}>
            Nessun pattern con questi filtri.
          </div>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between text-[11px]" style={{ color: 'var(--pi-muted)' }}>
        <button
          type="button"
          className="pi-btn"
          disabled={page === 0}
          onClick={() => setPage((p) => Math.max(0, p - 1))}
        >
          ← Precedenti
        </button>
        <span className="tabular-nums">
          {total === 0 ? 0 : page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} di{' '}
          {total.toLocaleString('it-IT')}
        </span>
        <button
          type="button"
          className="pi-btn"
          disabled={(page + 1) * PAGE_SIZE >= total}
          onClick={() => setPage((p) => p + 1)}
        >
          Successivi →
        </button>
      </div>
    </Section>
  )
}
