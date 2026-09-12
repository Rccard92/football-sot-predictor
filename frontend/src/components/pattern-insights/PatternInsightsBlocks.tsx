import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { Section, heatBg } from './PatternInsightsShell'
import type {
  ComplexityStat,
  FactorStat,
  MarketStat,
  QualityPoint,
  SampleBucket,
  SourceCoverage,
  SyntheticDirection,
} from '../../lib/patternInsightsApi'

const AXIS = { fill: '#8494b0', fontSize: 11 }
const GRID = '#1e2a44'
const TOOLTIP_STYLE = {
  background: '#131c31',
  border: '1px solid #1e2a44',
  borderRadius: 10,
  color: '#e8eef9',
  fontSize: 12,
}

function pct(v: number | null | undefined, d = 1): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(d)}%`
}

export function MarketValueBlock({ markets }: { markets: MarketStat[] }) {
  const chartData = useMemo(
    () =>
      [...markets]
        .filter((m) => m.best_roi_pct != null)
        .sort((a, b) => (b.best_roi_pct ?? 0) - (a.best_roi_pct ?? 0))
        .map((m) => ({ name: m.target_label, best: m.best_roi_pct ?? 0, median: m.median_roi_pct ?? 0 })),
    [markets],
  )
  const maxBest = Math.max(1, ...markets.map((m) => m.best_roi_pct ?? 0))
  const maxCount = Math.max(1, ...markets.map((m) => m.pattern_count))

  return (
    <Section
      title="Dove si concentra il valore"
      note="Miglior pattern e mediana per ciascun mercato con quota storica"
    >
      <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
        <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 26)}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 4, right: 30, top: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
            <XAxis type="number" unit="%" tick={AXIS} stroke={GRID} />
            <YAxis type="category" dataKey="name" width={148} tick={AXIS} stroke={GRID} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              cursor={{ fill: 'rgba(53,224,196,0.06)' }}
              formatter={(v, name) => [
                `${Number(v).toFixed(1)}%`,
                name === 'best' ? 'Miglior ROI' : 'ROI mediano',
              ]}
            />
            <Bar dataKey="best" fill="#35e0c4" radius={[0, 4, 4, 0]} />
            <Bar dataKey="median" fill="#3a5573" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>

        <div className="pi-scroll">
          <table className="pi-table">
            <thead>
              <tr>
                <th>Mercato</th>
                <th>Pattern</th>
                <th>Miglior ROI</th>
                <th>ROI mediano</th>
                <th>Camp. medio</th>
                <th>Quota media</th>
              </tr>
            </thead>
            <tbody>
              {markets.map((m) => (
                <tr key={m.target_key}>
                  <td className="font-semibold">{m.target_label}</td>
                  <td
                    className="tabular-nums"
                    style={{ background: heatBg(m.pattern_count, maxCount) }}
                  >
                    {m.pattern_count.toLocaleString('it-IT')}
                  </td>
                  <td
                    className="tabular-nums font-semibold"
                    style={{ background: heatBg(m.best_roi_pct, maxBest), color: 'var(--pi-pos)' }}
                  >
                    {pct(m.best_roi_pct)}
                  </td>
                  <td className="tabular-nums">{pct(m.median_roi_pct)}</td>
                  <td className="tabular-nums">{m.avg_n != null ? Math.round(m.avg_n) : '—'}</td>
                  <td className="tabular-nums">
                    {m.avg_quota != null ? m.avg_quota.toFixed(2) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  )
}

export function AnatomyBlock({
  factors,
  complexity,
}: {
  factors: FactorStat[]
  complexity: ComplexityStat[]
}) {
  const top = useMemo(() => factors.slice(0, 14).map((f) => ({ ...f })), [factors])
  const totalUses = factors.reduce((s, f) => s + f.uses, 0) || 1

  return (
    <Section
      title="Anatomia dei pattern"
      note="Quali condizioni pre-partita ricorrono di piu' e quanto pesa la complessita'"
    >
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.6fr_1fr]">
        <div>
          <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Frequenza con cui ogni fattore compare nei pattern trovati (quota sul totale delle
            condizioni usate).
          </div>
          <ResponsiveContainer width="100%" height={Math.max(280, top.length * 24)}>
            <BarChart data={top} layout="vertical" margin={{ left: 4, right: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
              <XAxis type="number" tick={AXIS} stroke={GRID} />
              <YAxis type="category" dataKey="label" width={230} tick={AXIS} stroke={GRID} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                cursor={{ fill: 'rgba(124,140,255,0.06)' }}
                formatter={(v) => [
                  `${Number(v).toLocaleString('it-IT')} usi (${((Number(v) / totalUses) * 100).toFixed(1)}%)`,
                  'Frequenza',
                ]}
              />
              <Bar dataKey="uses" fill="#7c8cff" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="space-y-3">
          <div className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Pattern semplici contro pattern combinati.
          </div>
          {complexity.map((c) => (
            <div key={c.atoms} className="pi-tile">
              <div className="flex items-baseline justify-between">
                <span className="text-sm font-semibold">
                  {c.atoms === 1 ? '1 condizione singola' : `${c.atoms} condizioni combinate`}
                </span>
                <span className="text-xs tabular-nums" style={{ color: 'var(--pi-muted)' }}>
                  {c.pattern_count.toLocaleString('it-IT')} pattern
                </span>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                <div>
                  <div style={{ color: 'var(--pi-muted)' }}>ROI medio</div>
                  <div className="tabular-nums font-semibold" style={{ color: 'var(--pi-pos)' }}>
                    {pct(c.avg_roi_pct)}
                  </div>
                </div>
                <div>
                  <div style={{ color: 'var(--pi-muted)' }}>Campione medio</div>
                  <div className="tabular-nums font-semibold">
                    {c.avg_n != null ? Math.round(c.avg_n) : '—'}
                  </div>
                </div>
              </div>
            </div>
          ))}
          {complexity.length >= 2 && (
            <div
              className="pi-tile text-[11px] leading-relaxed"
              style={{ color: 'var(--pi-muted)' }}
            >
              Se il ROI medio sale mentre il campione medio scende, la resa in piu&apos; dei pattern
              complessi e&apos; in buona parte sovra-adattamento, non valore reale.
            </div>
          )}
        </div>
      </div>
    </Section>
  )
}

export function SignalNoiseBlock({
  scatter,
  buckets,
}: {
  scatter: QualityPoint[]
  buckets: SampleBucket[]
}) {
  const maxCount = Math.max(1, ...buckets.map((b) => b.pattern_count))
  return (
    <Section
      title="Segnale o rumore?"
      note="I ROI piu' alti stanno sui campioni piu' piccoli: e' li' che si annida la fortuna"
    >
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.6fr_1fr]">
        <ResponsiveContainer width="100%" height={330}>
          <ScatterChart margin={{ left: 4, right: 20, top: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
            <XAxis
              type="number"
              dataKey="n"
              name="Campione"
              scale="log"
              domain={['dataMin', 'dataMax']}
              tick={AXIS}
              stroke={GRID}
              label={{ value: 'Campione (scala log)', position: 'insideBottom', offset: -6, fill: '#8494b0', fontSize: 11 }}
            />
            <YAxis
              type="number"
              dataKey="roi_pct"
              name="ROI"
              unit="%"
              tick={AXIS}
              stroke={GRID}
            />
            <ZAxis range={[24, 24]} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              cursor={{ strokeDasharray: '3 3', stroke: '#35e0c4' }}
              formatter={(v, name) => [
                name === 'ROI' ? `${Number(v).toFixed(1)}%` : Number(v).toLocaleString('it-IT'),
                name,
              ]}
            />
            <ReferenceLine y={0} stroke="#3a5573" />
            <Scatter data={scatter} fill="rgba(53,224,196,0.55)" />
          </ScatterChart>
        </ResponsiveContainer>

        <div className="space-y-2">
          <div className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Quanti pattern per fascia di campione.
          </div>
          {buckets.map((b) => (
            <div key={b.bucket} className="pi-tile">
              <div className="flex items-baseline justify-between text-xs">
                <span className="font-semibold">{b.bucket} partite</span>
                <span className="tabular-nums" style={{ color: 'var(--pi-muted)' }}>
                  {b.pattern_count.toLocaleString('it-IT')} · ROI medio {pct(b.avg_roi_pct)}
                </span>
              </div>
              <div className="mt-2 h-1.5 w-full rounded-full" style={{ background: '#1a2438' }}>
                <div
                  className="h-1.5 rounded-full"
                  style={{
                    width: `${(b.pattern_count / maxCount) * 100}%`,
                    background: b.bucket === '20-49' ? 'var(--pi-neg)' : 'var(--pi-accent)',
                  }}
                />
              </div>
            </div>
          ))}
          <div className="pi-tile text-[11px] leading-relaxed" style={{ color: 'var(--pi-muted)' }}>
            {buckets.some((b) => b.bucket === '20-49')
              ? 'La fascia piu’ bassa e’ in rosso perche’ con 20-49 partite bastano due o tre esiti fortunati per produrre un ROI apparentemente eccezionale.'
              : 'Nota come il ROI medio scenda man mano che il campione cresce: e’ il segno che gran parte del vantaggio apparente sulle fasce basse e’ varianza, non valore.'}
          </div>
        </div>
      </div>
    </Section>
  )
}

export function SituationsBlock({ situations }: { situations: SyntheticDirection[] }) {
  const data = useMemo(
    () =>
      situations.slice(0, 16).map((s) => ({
        name: s.target_label,
        up: s.best_up_pct ?? 0,
        down: s.best_down_pct ?? 0,
        baseline: s.baseline_pct,
        count: s.pattern_count,
      })),
    [situations],
  )
  return (
    <Section
      title="Situazioni piu' prevedibili (senza quota)"
      note="Quanto il profilo della partita sposta la probabilita' rispetto alla media generale"
    >
      <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
        A destra in verde quanto il pattern migliore alza la probabilita&apos;, a sinistra in rosso
        quanto il pattern opposto la abbassa. Sono statistiche di frequenza: non esiste quota storica
        su questi mercati, quindi non c&apos;e&apos; un ROI da calcolare.
      </div>
      <ResponsiveContainer width="100%" height={Math.max(320, data.length * 28)}>
        <BarChart data={data} layout="vertical" stackOffset="sign" margin={{ left: 4, right: 30 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
          <XAxis type="number" unit=" pt" tick={AXIS} stroke={GRID} />
          <YAxis type="category" dataKey="name" width={250} tick={AXIS} stroke={GRID} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: 'rgba(53,224,196,0.06)' }}
            formatter={(v, name) => [
              `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(1)} punti`,
              name === 'up' ? 'Spinta verso l&apos;alto' : 'Spinta verso il basso',
            ]}
          />
          <ReferenceLine x={0} stroke="#3a5573" />
          <Bar dataKey="down" fill="#f87171" radius={[4, 0, 0, 4]} />
          <Bar dataKey="up" fill="#34d399" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Section>
  )
}

export function DataFoundationBlock({ coverage }: { coverage: SourceCoverage }) {
  const comps = coverage.competitions ?? []
  const maxMatches = Math.max(1, ...comps.map((c) => c.matches))
  const markets = coverage.market_coverage ?? []

  return (
    <Section
      title="Base dati sotto l'analisi"
      note={
        coverage.quote_policy_version
          ? `Politica quote: ${coverage.quote_policy_version}`
          : undefined
      }
    >
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div>
          <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Partite per campionato e quante superano i requisiti pre-partita (eleggibili).
          </div>
          <div className="pi-scroll" style={{ maxHeight: 360 }}>
            <table className="pi-table">
              <thead>
                <tr>
                  <th>Campionato</th>
                  <th>Partite</th>
                  <th>Eleggibili</th>
                  <th>Quota eleggibili</th>
                </tr>
              </thead>
              <tbody>
                {comps.map((c) => {
                  const ratio = c.matches ? (c.eligible_core / c.matches) * 100 : 0
                  return (
                    <tr key={c.competition}>
                      <td className="font-semibold">{c.competition}</td>
                      <td
                        className="tabular-nums"
                        style={{ background: heatBg(c.matches, maxMatches) }}
                      >
                        {c.matches.toLocaleString('it-IT')}
                      </td>
                      <td className="tabular-nums">{c.eligible_core.toLocaleString('it-IT')}</td>
                      <td className="tabular-nums">{ratio.toFixed(0)}%</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Copertura quote Bet365 per mercato: quanto del campione ha davvero una quota storica.
          </div>
          <div className="pi-scroll" style={{ maxHeight: 360 }}>
            <table className="pi-table">
              <thead>
                <tr>
                  <th>Mercato</th>
                  <th>Righe</th>
                  <th>Con quota</th>
                  <th>Copertura</th>
                </tr>
              </thead>
              <tbody>
                {markets.map((m) => (
                  <tr key={m.market_key}>
                    <td className="font-semibold">{m.market_key}</td>
                    <td className="tabular-nums">{m.rows.toLocaleString('it-IT')}</td>
                    <td className="tabular-nums">{m.rows_with_quote.toLocaleString('it-IT')}</td>
                    <td
                      className="tabular-nums font-semibold"
                      style={{ background: heatBg(m.quote_coverage_pct, 100) }}
                    >
                      {m.quote_coverage_pct?.toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Section>
  )
}
