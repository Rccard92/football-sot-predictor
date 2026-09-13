import { useCallback, useEffect, useState } from 'react'
import { Section } from './PatternInsightsShell'
import { PatternDetailPanel } from './PatternDetailPanel'
import { ABOVE_CHANCE, BELOW_CHANCE } from './PatternValidationBlocks'
import {
  VERDICT_LABELS,
  getPatternInsightCandidates,
  type OosStats,
  type PatternInsightCandidate,
  type PatternInsightTargetType,
  type PatternSort,
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

export function VerdictChip({ verdict }: { verdict: OosStats['verdict'] | null | undefined }) {
  if (!verdict) return <span style={{ color: 'var(--pi-muted)' }}>—</span>
  const color =
    verdict === 'confirmed'
      ? ABOVE_CHANCE
      : verdict === 'rejected'
        ? BELOW_CHANCE
        : verdict === 'attenuated'
          ? 'var(--pi-warn)'
          : 'var(--pi-muted)'
  const icon = verdict === 'confirmed' ? '✓' : verdict === 'rejected' ? '✗' : verdict === 'attenuated' ? '~' : '·'
  return (
    <span
      className="whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold"
      style={{ color: 'var(--pi-text)', background: 'rgba(255,255,255,0.03)', border: `1px solid ${color}` }}
    >
      <span style={{ color }}>{icon}</span> {VERDICT_LABELS[verdict]}
    </span>
  )
}

function MetricCell({ isMarket, roi, deviation }: { isMarket: boolean; roi: number | null; deviation: number | null }) {
  const v = isMarket ? roi : deviation
  return (
    <span className="font-semibold" style={{ color: (v ?? 0) >= 0 ? 'var(--pi-text)' : BELOW_CHANCE }}>
      {pct(v)}
    </span>
  )
}

function Row({
  c,
  onOpen,
  hasValidation,
}: {
  c: PatternInsightCandidate
  onOpen: () => void
  hasValidation: boolean
}) {
  const isMarket = c.target_type === 'market'
  const oos = c.oos
  return (
    <tr onClick={onOpen} style={{ cursor: 'pointer' }} title="Apri dettaglio: stagioni, campionati e partite">
      <td className="whitespace-nowrap font-semibold">{c.target_label}</td>
      <td style={{ maxWidth: 380 }}>
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
          {c.wins}V · {c.losses}P · {c.win_rate_pct?.toFixed(1)}%
        </div>
      </td>
      <td className="whitespace-nowrap tabular-nums">
        <MetricCell isMarket={isMarket} roi={c.roi_pct} deviation={c.deviation_pct} />
        {isMarket && c.avg_quota != null ? (
          <div className="text-[10px]" style={{ color: 'var(--pi-muted)' }}>
            quota {c.avg_quota.toFixed(2)}
          </div>
        ) : null}
      </td>
      {hasValidation && (
        <>
          <td className="whitespace-nowrap tabular-nums" style={{ borderLeft: '1px solid var(--pi-border)' }}>
            {oos ? (
              <>
                <div>{oos.n}</div>
                <div className="text-[10px]" style={{ color: 'var(--pi-muted)' }}>
                  {oos.wins}V · {oos.losses}P · {oos.win_rate_pct?.toFixed(1)}%
                </div>
              </>
            ) : (
              '—'
            )}
          </td>
          <td className="whitespace-nowrap tabular-nums">
            {oos ? (
              <>
                <MetricCell isMarket={isMarket} roi={oos.roi_pct} deviation={oos.deviation_pct} />
                {isMarket && oos.avg_quota != null ? (
                  <div className="text-[10px]" style={{ color: 'var(--pi-muted)' }}>
                    quota {oos.avg_quota.toFixed(2)}
                  </div>
                ) : null}
              </>
            ) : (
              '—'
            )}
          </td>
          <td className="whitespace-nowrap">
            <VerdictChip verdict={oos?.verdict} />
            {oos?.null_confirm_prob != null && oos.verdict !== 'insufficient_sample' ? (
              <div className="mt-0.5 text-[10px]" style={{ color: 'var(--pi-muted)' }}>
                caso: {(oos.null_confirm_prob * 100).toFixed(0)}%
              </div>
            ) : null}
          </td>
        </>
      )}
    </tr>
  )
}

export function PatternExplorer({ defaultMinN = 50 }: { defaultMinN?: number }) {
  const [targetType, setTargetType] = useState<'ALL' | PatternInsightTargetType>('market')
  const [minN, setMinN] = useState(defaultMinN)
  const [verdict, setVerdict] = useState<'ALL' | OosStats['verdict']>('ALL')
  const [sort, setSort] = useState<PatternSort>('best')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [items, setItems] = useState<PatternInsightCandidate[]>([])
  const [validationSeason, setValidationSeason] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [detailId, setDetailId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getPatternInsightCandidates({
        targetType: targetType === 'ALL' ? undefined : targetType,
        minN,
        verdict: verdict === 'ALL' ? undefined : verdict,
        sort,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      setTotal(res.total)
      setItems(res.items)
      setValidationSeason(res.validation?.season_label ?? null)
    } finally {
      setLoading(false)
    }
  }, [targetType, minN, verdict, sort, page])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setPage(0)
  }, [targetType, minN, verdict, sort])

  const hasValidation = validationSeason != null

  return (
    <Section
      title="Esplora i pattern"
      note={`${total.toLocaleString('it-IT')} pattern con i filtri attuali · clicca una riga per il dettaglio`}
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
        {hasValidation && (
          <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Verdetto {validationSeason}
            <select
              className="pi-select"
              value={verdict}
              onChange={(e) => setVerdict(e.target.value as typeof verdict)}
            >
              <option value="ALL">Tutti</option>
              <option value="confirmed">Confermati</option>
              <option value="attenuated">Attenuati</option>
              <option value="rejected">Respinti</option>
              <option value="insufficient_sample">Campione insufficiente</option>
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          Campione minimo (scoperta)
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
          <select className="pi-select" value={sort} onChange={(e) => setSort(e.target.value as PatternSort)}>
            <option value="best">Automatico (scoperta)</option>
            <option value="roi_desc">ROI scoperta</option>
            <option value="deviation_desc">Scarto scoperta</option>
            {hasValidation && <option value="oos_roi_desc">ROI {validationSeason}</option>}
            {hasValidation && <option value="oos_deviation_desc">Scarto {validationSeason}</option>}
            {hasValidation && <option value="oos_n_desc">Campione {validationSeason}</option>}
          </select>
        </label>
      </div>

      <div className="pi-scroll" style={{ maxHeight: 620 }}>
        <table className="pi-table">
          <thead>
            <tr>
              <th rowSpan={hasValidation ? 2 : 1}>Bersaglio</th>
              <th rowSpan={hasValidation ? 2 : 1}>Pattern</th>
              {hasValidation ? (
                <>
                  <th colSpan={2} style={{ color: '#b9adf2' }}>Scoperta</th>
                  <th colSpan={3} style={{ color: '#7fd9c8', borderLeft: '1px solid var(--pi-border)' }}>
                    Verifica {validationSeason}
                  </th>
                </>
              ) : (
                <>
                  <th>Campione</th>
                  <th>ROI / Scarto</th>
                </>
              )}
            </tr>
            {hasValidation && (
              <tr>
                <th style={{ top: 30 }}>Campione</th>
                <th style={{ top: 30 }}>ROI / Scarto</th>
                <th style={{ top: 30, borderLeft: '1px solid var(--pi-border)' }}>Campione</th>
                <th style={{ top: 30 }}>ROI / Scarto</th>
                <th style={{ top: 30 }}>Verdetto</th>
              </tr>
            )}
          </thead>
          <tbody>
            {items.map((c) => (
              <Row key={c.id} c={c} onOpen={() => setDetailId(c.id)} hasValidation={hasValidation} />
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

      {detailId != null && (
        <PatternDetailPanel candidateId={detailId} onClose={() => setDetailId(null)} />
      )}
    </Section>
  )
}
