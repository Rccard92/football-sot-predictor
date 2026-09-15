import { Fragment, useEffect, useMemo, useState } from 'react'
import { PageShell, Section } from '../components/layout/PageShell'
import {
  getObservationDashboard,
  type EngineMetrics,
  type ObservationDashboard,
  type ObservationModelOverview,
  type ObservationModelsOverview,
  type ObservationTally,
  type ObservationTallyRow,
} from '../lib/cecchinoLiveApi'
import { MARKET_LABELS } from '../lib/masterPatternApi'
import { formatFetchError } from '../utils/formatFetchError'

/**
 * Osservazione live divisa per modello. Due strade per ogni modello, sempre separate:
 * indice di acquistabilità (predizioni 70+ con quota da 1,50) e pattern con quota.
 */

const TEXT_MUTED = 'var(--pi-muted)'
const COLOR_POS = 'var(--pi-pos)'
const COLOR_NEG = 'var(--pi-neg)'
const MODEL_ORDER = ['V2', 'V2.5', 'V3'] as const
/** Colori fissi per modello (mai riassegnati per posizione). */
const MODEL_COLORS: Record<string, string> = { V2: '#7c8cff', 'V2.5': '#35e0c4', V3: '#fbbf24' }
const FAMILIES = ['1X2', 'Over/Under 2.5', 'Doppia chance', '1X2 primo tempo'] as const

// testo base 16px e titoli più grandi, solo in questa pagina
const PAGE_CSS = `
  .obs-root { font-size: 16px; }
  .obs-root .pi-section { padding: 22px; }
  .obs-root .pi-section-title { font-size: 20px; letter-spacing: 0.06em; }
  .obs-root .pi-tile { padding: 16px 18px; }
  .obs-root .pi-table { font-size: 15px; }
  .obs-root .pi-table th { font-size: 13px; letter-spacing: 0.04em; padding: 10px 12px; }
  .obs-root .pi-table td { padding: 10px 12px; }
  .obs-root .pi-select, .obs-root .pi-btn { font-size: 15px; }
`

type Period = '7' | '30' | '90' | 'all'
const PERIODS: { value: Period; label: string }[] = [
  { value: '7', label: 'Ultimi 7 giorni' },
  { value: '30', label: 'Ultimi 30 giorni' },
  { value: '90', label: 'Ultimi 90 giorni' },
  { value: 'all', label: 'Tutto il registro' },
]

const SEGNO: Record<string, string> = {
  HOME: '1', DRAW: 'X', AWAY: '2', ONE_X: '1X', X_TWO: 'X2', ONE_TWO: '12',
  HOME_PT: '1 PT', DRAW_PT: 'X PT', AWAY_PT: '2 PT',
  OVER_0_5: 'Over 0.5', UNDER_0_5: 'Under 0.5', OVER_1_5: 'Over 1.5', UNDER_1_5: 'Under 1.5',
  OVER_2_5: 'Over 2.5', UNDER_2_5: 'Under 2.5', OVER_3_5: 'Over 3.5', UNDER_3_5: 'Under 3.5',
}

const PATTERN_BUCKETS: { key: keyof ObservationModelOverview['index']['by_pattern']; label: string }[] = [
  { key: 'confermate', label: 'Confermate da un pattern' },
  { key: 'in_contrasto', label: 'In contrasto con un pattern' },
  { key: 'altri_pattern', label: 'Pattern su altri mercati' },
  { key: 'senza_pattern', label: 'Nessun pattern acceso' },
]

const AGREEMENT_ROWS: { key: string; label: string }[] = [
  { key: 'entrambi_90+', label: 'V2.5 e V3 entrambi 90+' },
  { key: 'entrambi_70+', label: 'V2.5 e V3 entrambi 70+' },
  { key: 'V3_90+_e_V2.5_sotto_50', label: 'V3 90+ e V2.5 sotto 50' },
  { key: 'V2.5_90+_e_V3_sotto_50', label: 'V2.5 90+ e V3 sotto 50' },
]

function num(v: number | null | undefined, d = 1): string {
  return v == null ? '—' : v.toLocaleString('it-IT', { minimumFractionDigits: d, maximumFractionDigits: d })
}

function signed(v: number | null | undefined, d = 1, suffix = '%'): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${num(v, d)}${suffix}`
}

function tone(v: number | null | undefined): string | undefined {
  return v == null ? undefined : v >= 0 ? COLOR_POS : COLOR_NEG
}

function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

function shortDate(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${d}/${m}`
}

function marketLabel(key: string): string {
  return SEGNO[key] ?? MARKET_LABELS[key] ?? key
}

function SampleChip({ t }: { t: ObservationTally }) {
  const color = t.sample === 'affidabile' ? COLOR_POS : t.sample === 'indicativo' ? 'var(--pi-warn)' : TEXT_MUTED
  return (
    <span className="whitespace-nowrap rounded px-2 py-0.5 text-[13px] font-semibold" style={{ border: `1px solid ${color}`, color }}>
      {t.sample}
    </span>
  )
}

function WonLost({ t }: { t: ObservationTally }) {
  return (
    <span className="tabular-nums">
      {t.won} · {t.lost}
      {t.pending ? <span style={{ color: TEXT_MUTED }}> · {t.pending} in attesa</span> : null}
    </span>
  )
}

// --- intestazione: chi sta rendendo di più ----------------------------------------------------

function bestModel(overview: ObservationModelsOverview, road: 'index' | 'patterns'): { model: string; t: ObservationTally } | null {
  let best: { model: string; t: ObservationTally } | null = null
  for (const model of MODEL_ORDER) {
    const m = overview.models[model]
    if (!m) continue
    const t = road === 'index' ? m.index.plays : m.patterns.plays
    if (road === 'index' && !m.index.available) continue
    if (!t.closed || t.roi_pct == null) continue
    if (!best || t.roi_pct > (best.t.roi_pct ?? -Infinity)) best = { model, t }
  }
  return best
}

function Headline({ overview }: { overview: ObservationModelsOverview }) {
  const lines = (['index', 'patterns'] as const).map((road) => {
    const best = bestModel(overview, road)
    const name = road === 'index' ? 'Indice di acquistabilità' : 'Pattern con quota'
    if (!best) return { road, text: `${name}: nessuna giocata chiusa nel periodo.`, best }
    return {
      road,
      best,
      text: `${name}: va meglio la ${best.model} — ROI ${signed(best.t.roi_pct)} su ${best.t.closed} giocate chiuse (${best.t.sample}).`,
    }
  })
  return (
    <div className="pi-tile space-y-2">
      {lines.map((l) => (
        <p key={l.road} className="text-lg leading-relaxed">
          {l.best ? <span className="mr-2 inline-block h-3 w-3 rounded-full align-middle" style={{ background: MODEL_COLORS[l.best.model] }} /> : null}
          {l.text}
        </p>
      ))}
      <p className="text-[15px]" style={{ color: TEXT_MUTED }}>
        Sotto {overview.thresholds.sample_early} giocate chiuse i numeri sono quasi sempre fortuna; da {overview.thresholds.sample_reliable} iniziano a
        essere affidabili. Profitto a 1 unità per giocata, alla quota registrata prima della partita.
      </p>
    </div>
  )
}

// --- schede dei modelli ------------------------------------------------------------------------

function RoadBlock({ title, t, last7, children }: { title: string; t: ObservationTally; last7: ObservationTally; children?: React.ReactNode }) {
  return (
    <div className="space-y-2 border-t pt-3" style={{ borderColor: 'var(--pi-border)' }}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[15px] font-bold uppercase tracking-wide" style={{ color: TEXT_MUTED }}>
          {title}
        </span>
        <SampleChip t={t} />
      </div>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-3xl font-bold tabular-nums" style={{ color: tone(t.roi_pct) }}>
          {signed(t.roi_pct)}
        </span>
        <span className="tabular-nums" style={{ color: tone(t.profit) }}>
          {signed(t.profit, 2, ' u')}
        </span>
      </div>
      <div className="text-[15px]" style={{ color: TEXT_MUTED }}>
        Vinte {num(t.won_pct)}% · <WonLost t={t} /> · quota media {num(t.avg_quota, 2)}
      </div>
      <div className="text-[15px]" style={{ color: TEXT_MUTED }}>
        Ultimi 7 giorni: <span style={{ color: tone(last7.roi_pct) }}>{signed(last7.roi_pct)}</span> su {last7.closed} chiuse
      </div>
      {children}
    </div>
  )
}

function ModelCard({ model, m }: { model: string; m: ObservationModelOverview | undefined }) {
  return (
    <div className="pi-tile space-y-3">
      <div className="flex items-center gap-2 text-xl font-bold">
        <span className="inline-block h-3 w-3 rounded-full" style={{ background: MODEL_COLORS[model] }} />
        {model}
      </div>
      {!m ? (
        <p style={{ color: TEXT_MUTED }}>Nessuna previsione registrata nel periodo.</p>
      ) : (
        <>
          {m.index.available ? (
            <RoadBlock title="Indice · 70+ con quota da 1,50" t={m.index.plays} last7={m.index.last7}>
              <div className="grid grid-cols-2 gap-2 text-[15px]">
                <div>
                  90–100: <span style={{ color: tone(m.index.top['90-100'].roi_pct) }}>{signed(m.index.top['90-100'].roi_pct)}</span>{' '}
                  <span style={{ color: TEXT_MUTED }}>({m.index.top['90-100'].closed})</span>
                </div>
                <div>
                  70–90: <span style={{ color: tone(m.index.top['70-90'].roi_pct) }}>{signed(m.index.top['70-90'].roi_pct)}</span>{' '}
                  <span style={{ color: TEXT_MUTED }}>({m.index.top['70-90'].closed})</span>
                </div>
                <div>
                  Confermate: <span style={{ color: tone(m.index.by_pattern.confermate.roi_pct) }}>{signed(m.index.by_pattern.confermate.roi_pct)}</span>{' '}
                  <span style={{ color: TEXT_MUTED }}>({m.index.by_pattern.confermate.closed})</span>
                </div>
                <div>
                  Senza pattern:{' '}
                  <span style={{ color: tone(m.index.by_pattern.senza_pattern.roi_pct) }}>{signed(m.index.by_pattern.senza_pattern.roi_pct)}</span>{' '}
                  <span style={{ color: TEXT_MUTED }}>({m.index.by_pattern.senza_pattern.closed})</span>
                </div>
              </div>
            </RoadBlock>
          ) : (
            <div className="border-t pt-3 text-[15px]" style={{ borderColor: 'var(--pi-border)', color: TEXT_MUTED }}>
              {model === 'V2'
                ? 'Indice orchestratore non previsto per la V2 (modello congelato).'
                : `Nessuna predizione dell'indice ${model} registrata nel periodo: le prime arrivano con le scansioni dal 16/09.`}
            </div>
          )}
          <RoadBlock title="Pattern con quota" t={m.patterns.plays} last7={m.patterns.last7} />
        </>
      )}
    </div>
  )
}

// --- profitto cumulato --------------------------------------------------------------------------

function CumulativeProfitChart({ overview }: { overview: ObservationModelsOverview }) {
  const [road, setRoad] = useState<'index' | 'patterns'>('index')
  const [hover, setHover] = useState<number | null>(null)
  const models = MODEL_ORDER.filter((m) => overview.models[m] && (road === 'patterns' || overview.models[m].index.available))
  const dates = [...new Set(models.flatMap((m) => overview.models[m].daily.map((d) => d.scan_date)))].sort()
  const series = Object.fromEntries(
    models.map((m) => {
      const byDate = new Map(overview.models[m].daily.map((d) => [d.scan_date, road === 'index' ? d.cumulative_index_profit : d.cumulative_pattern_profit]))
      let last = 0
      return [m, dates.map((d) => (byDate.has(d) ? (last = byDate.get(d) as number) : last))]
    }),
  ) as Record<string, number[]>
  const all = Object.values(series).flat()

  const header = (
    <div className="mb-3 flex flex-wrap items-center gap-3">
      <button type="button" className="pi-btn" aria-pressed={road === 'index'} style={{ borderColor: road === 'index' ? 'var(--pi-accent)' : undefined }} onClick={() => setRoad('index')}>
        Indice
      </button>
      <button type="button" className="pi-btn" aria-pressed={road === 'patterns'} style={{ borderColor: road === 'patterns' ? 'var(--pi-accent)' : undefined }} onClick={() => setRoad('patterns')}>
        Pattern
      </button>
      <div className="flex flex-wrap gap-4 text-[15px]" style={{ color: TEXT_MUTED }}>
        {models.map((m) => (
          <span key={m} className="inline-flex items-center gap-1.5">
            <svg width="18" height="6" aria-hidden>
              <line x1="0" y1="3" x2="18" y2="3" stroke={MODEL_COLORS[m]} strokeWidth="2" />
            </svg>
            {m}
          </span>
        ))}
      </div>
    </div>
  )

  if (dates.length < 2 || all.length === 0) {
    return (
      <div>
        {header}
        <p style={{ color: TEXT_MUTED }}>Il grafico compare dal secondo giorno con giocate registrate.</p>
      </div>
    )
  }
  const W = 720
  const H = 240
  const pad = { l: 52, r: 12, t: 12, b: 28 }
  const lo = Math.min(0, ...all)
  const hi = Math.max(0, ...all)
  const span = hi - lo || 1
  const yMin = lo - span * 0.1
  const yMax = hi + span * 0.1
  const x = (i: number) => pad.l + (i * (W - pad.l - pad.r)) / (dates.length - 1)
  const y = (v: number) => pad.t + ((yMax - v) * (H - pad.t - pad.b)) / (yMax - yMin)
  const ticks = [yMin + (yMax - yMin) * 0.15, 0, yMax - (yMax - yMin) * 0.15]

  return (
    <div>
      {header}
      <div className="relative overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[520px]" role="img" aria-label="Profitto cumulato per modello" onMouseLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke={t === 0 ? '#8494b0' : '#1e2a44'} strokeWidth="1" />
              <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize="11" fill="#8494b0">
                {t === 0 ? '0' : `${t > 0 ? '+' : ''}${t.toFixed(1)}`}
              </text>
            </g>
          ))}
          {dates.map((d, i) => (
            <text key={d} x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="#8494b0">
              {dates.length <= 14 || i % Math.ceil(dates.length / 14) === 0 ? shortDate(d) : ''}
            </text>
          ))}
          {models.map((m) => (
            <path key={m} d={`M ${series[m].map((v, i) => `${x(i)},${y(v)}`).join(' L ')}`} fill="none" stroke={MODEL_COLORS[m]} strokeWidth="2" strokeLinejoin="round" />
          ))}
          {hover != null && <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={H - pad.b} stroke="#8494b0" strokeWidth="1" />}
          {hover != null &&
            models.map((m) => <circle key={m} cx={x(hover)} cy={y(series[m][hover])} r="4" fill={MODEL_COLORS[m]} stroke="#0e1526" strokeWidth="2" />)}
          {dates.map((d, i) => (
            <rect
              key={d}
              x={x(i) - (W - pad.l - pad.r) / (2 * (dates.length - 1))}
              y={pad.t}
              width={(W - pad.l - pad.r) / (dates.length - 1)}
              height={H - pad.t - pad.b}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            />
          ))}
        </svg>
        {hover != null && (
          <div className="pi-tile pointer-events-none absolute right-2 top-2 text-[14px] tabular-nums">
            <div className="font-semibold">{shortDate(dates[hover])} · profitto cumulato</div>
            {models.map((m) => (
              <div key={m} style={{ color: TEXT_MUTED }}>
                {m}: <span style={{ color: tone(series[m][hover]) }}>{signed(series[m][hover], 2, ' u')}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// --- tabelle -----------------------------------------------------------------------------------

function TallyTable({ rows, first, empty, labelOf }: { rows: ObservationTallyRow[]; first: string; empty: string; labelOf?: (r: ObservationTallyRow) => string }) {
  if (rows.length === 0) return <p style={{ color: TEXT_MUTED }}>{empty}</p>
  return (
    <div className="pi-scroll" style={{ maxHeight: 420 }}>
      <table className="pi-table">
        <thead>
          <tr>
            <th>{first}</th>
            <th className="text-right">Giocate</th>
            <th className="text-right">Vinte · perse</th>
            <th className="text-right">% vinte</th>
            <th className="text-right">ROI</th>
            <th className="text-right">Profitto</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td className="font-medium">{labelOf ? labelOf(r) : (r.label ?? r.key)}</td>
              <td className="text-right tabular-nums">{r.plays}</td>
              <td className="whitespace-nowrap text-right">
                <WonLost t={r} />
              </td>
              <td className="text-right tabular-nums">{num(r.won_pct)}</td>
              <td className="text-right tabular-nums" style={{ color: tone(r.roi_pct) }}>
                {signed(r.roi_pct)}
              </td>
              <td className="text-right tabular-nums" style={{ color: tone(r.profit) }}>
                {signed(r.profit, 2, ' u')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DailyTable({ m, showIndex }: { m: ObservationModelOverview; showIndex: boolean }) {
  const [open, setOpen] = useState<string | null>(null)
  const days = [...m.daily].reverse()
  if (days.length === 0) return <p style={{ color: TEXT_MUTED }}>Nessuna giornata registrata nel periodo.</p>
  return (
    <div className="pi-scroll" style={{ maxHeight: 560 }}>
      <table className="pi-table">
        <thead>
          <tr>
            <th>Giornata</th>
            {showIndex && <th className="text-right">Indice · vinte · perse</th>}
            {showIndex && <th className="text-right">Indice profitto (cumulato)</th>}
            <th className="text-right">Pattern · vinte · perse</th>
            <th className="text-right">Pattern profitto (cumulato)</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {days.map((d) => (
            <Fragment key={d.scan_date}>
              <tr>
                <td className="font-medium">{shortDate(d.scan_date)}</td>
                {showIndex && (
                  <td className="whitespace-nowrap text-right">
                    <WonLost t={d.index} />
                  </td>
                )}
                {showIndex && (
                  <td className="whitespace-nowrap text-right tabular-nums">
                    <span style={{ color: tone(d.index.profit) }}>{signed(d.index.profit, 2, ' u')}</span>{' '}
                    <span style={{ color: TEXT_MUTED }}>({signed(d.cumulative_index_profit, 2, ' u')})</span>
                  </td>
                )}
                <td className="whitespace-nowrap text-right">
                  <WonLost t={d.pattern} />
                </td>
                <td className="whitespace-nowrap text-right tabular-nums">
                  <span style={{ color: tone(d.pattern.profit) }}>{signed(d.pattern.profit, 2, ' u')}</span>{' '}
                  <span style={{ color: TEXT_MUTED }}>({signed(d.cumulative_pattern_profit, 2, ' u')})</span>
                </td>
                <td className="text-right">
                  {d.fixtures.length > 0 && (
                    <button type="button" className="pi-btn" onClick={() => setOpen(open === d.scan_date ? null : d.scan_date)} aria-expanded={open === d.scan_date}>
                      {open === d.scan_date ? 'Chiudi' : `${d.fixtures.length} partite`}
                    </button>
                  )}
                </td>
              </tr>
              {open === d.scan_date && (
                <tr>
                  <td colSpan={showIndex ? 6 : 4}>
                    <ul className="space-y-2">
                      {d.fixtures.map((f) => (
                        <li key={f.today_fixture_id} className="pi-tile">
                          <div className="font-semibold">
                            {f.match}{' '}
                            <span className="font-normal" style={{ color: TEXT_MUTED }}>
                              · {f.league}
                              {f.score && f.score.ft_home != null ? ` · ${f.score.ft_home}-${f.score.ft_away}` : ''}
                            </span>
                          </div>
                          <div className="mt-1 flex flex-wrap gap-2 text-[14px]">
                            {showIndex &&
                              f.index.map((p) => (
                                <span key={`i-${p.market_key}`} className="rounded px-2 py-0.5" style={{ border: '1px solid var(--pi-border)', opacity: p.playable ? 1 : 0.6 }}>
                                  Indice {marketLabel(p.market_key)} {Math.round(p.score)} · q {num(p.quota, 2)}{' '}
                                  <Outcome won={p.won} />
                                </span>
                              ))}
                            {f.patterns.map((p) => (
                              <span key={`p-${p.market_key}`} className="rounded px-2 py-0.5" style={{ border: '1px solid var(--pi-border)' }}>
                                Pattern {marketLabel(p.market_key)} ×{p.patterns} · q {num(p.quota, 2)} <Outcome won={p.won} />
                              </span>
                            ))}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Outcome({ won }: { won: boolean | null }) {
  if (won == null) return <span style={{ color: TEXT_MUTED }}>in attesa</span>
  return <span style={{ color: won ? COLOR_POS : COLOR_NEG, fontWeight: 600 }}>{won ? 'vinta' : 'persa'}</span>
}

function ModelDetail({ model, m }: { model: string; m: ObservationModelOverview }) {
  const [where, setWhere] = useState<'index' | 'patterns'>(m.index.available ? 'index' : 'patterns')
  const whereData = where === 'index' ? m.index : m.patterns
  return (
    <div className="space-y-5">
      {m.index.available && (
        <div className="grid gap-4 xl:grid-cols-2">
          <div>
            <h3 className="mb-2 text-lg font-semibold">Indice · fasce di punteggio</h3>
            <p className="mb-2 text-[15px]" style={{ color: TEXT_MUTED }}>
              Tutti i mercati con punteggio, qualunque quota: dice se punteggi più alti vincono davvero di più.
            </p>
            <TallyTable rows={[...m.index.bands].reverse()} first="Fascia" empty="Nessun punteggio registrato." />
          </div>
          <div>
            <h3 className="mb-2 text-lg font-semibold">Indice · conferma dei pattern</h3>
            <p className="mb-2 text-[15px]" style={{ color: TEXT_MUTED }}>
              Solo giocate (70+ con quota da 1,50). Contano i pattern costruiti sui moduli.
            </p>
            <TallyTable
              rows={PATTERN_BUCKETS.map((b) => ({ key: b.key, label: b.label, ...m.index.by_pattern[b.key] }))}
              first="Predizioni"
              empty="Nessuna giocata."
            />
          </div>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-lg font-semibold">Pattern con quota · per mercato</h3>
        {m.patterns.by_market.length === 0 ? (
          <p style={{ color: TEXT_MUTED }}>Nessun pattern con quota acceso nel periodo.</p>
        ) : (
          <div className="pi-scroll" style={{ maxHeight: 420 }}>
            <table className="pi-table min-w-[760px]">
              <thead>
                <tr>
                  <th>Mercato</th>
                  <th className="text-right">Segnali</th>
                  <th className="text-right">Vinti · persi</th>
                  <th className="text-right">% live</th>
                  <th className="text-right">% storico</th>
                  <th className="text-right">ROI live</th>
                  <th className="text-right">ROI storico</th>
                  <th className="text-right">Quota media</th>
                </tr>
              </thead>
              <tbody>
                {m.patterns.by_market.map((r) => (
                  <tr key={r.key}>
                    <td className="font-medium">{marketLabel(r.key)}</td>
                    <td className="text-right tabular-nums">{r.plays}</td>
                    <td className="whitespace-nowrap text-right">
                      <WonLost t={r} />
                    </td>
                    <td className="text-right tabular-nums">{num(r.won_pct)}</td>
                    <td className="text-right tabular-nums" style={{ color: TEXT_MUTED }}>
                      {num(r.hist_win_pct)}
                    </td>
                    <td className="text-right tabular-nums" style={{ color: tone(r.roi_pct) }}>
                      {signed(r.roi_pct)}
                    </td>
                    <td className="text-right tabular-nums" style={{ color: TEXT_MUTED }}>
                      {signed(r.hist_roi_pct)}
                    </td>
                    <td className="text-right tabular-nums">{num(r.avg_quota, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          <TallyTable rows={m.patterns.concordance} first="Pattern concordi" empty="Nessun segnale." />
          <div className="pi-tile text-[15px]">
            <div className="font-semibold">Pattern che usano la quota come condizione (a parte)</div>
            <div className="mt-1" style={{ color: TEXT_MUTED }}>
              {m.patterns.with_book_conditions.plays} segnali · vinte {num(m.patterns.with_book_conditions.won_pct)}% · ROI{' '}
              <span style={{ color: tone(m.patterns.with_book_conditions.roi_pct) }}>{signed(m.patterns.with_book_conditions.roi_pct)}</span>
            </div>
          </div>
        </div>
      </div>

      <div>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h3 className="text-lg font-semibold">Dove guadagna e dove perde</h3>
          {m.index.available && (
            <>
              <button type="button" className="pi-btn" aria-pressed={where === 'index'} style={{ borderColor: where === 'index' ? 'var(--pi-accent)' : undefined }} onClick={() => setWhere('index')}>
                Indice
              </button>
              <button type="button" className="pi-btn" aria-pressed={where === 'patterns'} style={{ borderColor: where === 'patterns' ? 'var(--pi-accent)' : undefined }} onClick={() => setWhere('patterns')}>
                Pattern
              </button>
            </>
          )}
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          <TallyTable rows={whereData.by_market} first="Mercato" empty="Nessuna giocata." labelOf={(r) => marketLabel(r.key)} />
          <TallyTable rows={whereData.by_family} first="Famiglia" empty="Nessuna giocata." />
          <TallyTable rows={whereData.by_league} first="Campionato" empty="Nessuna giocata." />
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-lg font-semibold">Giornata per giornata · {model}</h3>
        <DailyTable m={m} showIndex={m.index.available} />
      </div>
    </div>
  )
}

function EngineTable({ engines, models }: { engines: EngineMetrics; models: string[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="pi-table min-w-[720px]">
        <thead>
          <tr>
            <th>Modello</th>
            {FAMILIES.map((f) => (
              <th key={f} className="text-right">
                {f}
                <div className="normal-case tracking-normal">errore · favorito</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m}>
              <td className="whitespace-nowrap font-semibold">
                <span className="mr-2 inline-block h-2 w-2 rounded-full align-middle" style={{ background: MODEL_COLORS[m] ?? '#e8eef9' }} />
                {m}
              </td>
              {FAMILIES.map((f) => {
                const cell = engines[m]?.[f]
                if (!cell || cell.fixtures === 0) {
                  return (
                    <td key={f} className="text-right" style={{ color: TEXT_MUTED }}>
                      —
                    </td>
                  )
                }
                return (
                  <td key={f} className="whitespace-nowrap text-right tabular-nums">
                    {num(cell.brier, 4)}
                    <span style={{ color: TEXT_MUTED }}> · {num(cell.favourite_hit_pct, 0)}%</span>
                    <div className="text-[13px]" style={{ color: TEXT_MUTED }}>
                      {cell.fixtures} partite
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function LiveObservationPage() {
  const [period, setPeriod] = useState<Period>('30')
  const [data, setData] = useState<ObservationDashboard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<string>('V3')

  useEffect(() => {
    let alive = true
    setData(null)
    setError(null)
    const from = period === 'all' ? null : isoDaysAgo(Number(period))
    getObservationDashboard(from, null)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(formatFetchError(e)))
    return () => {
      alive = false
    }
  }, [period])

  const overview = data?.models_overview
  const tabs = useMemo(() => MODEL_ORDER.filter((m) => overview?.models[m]), [overview])
  const current = tabs.includes(tab as (typeof MODEL_ORDER)[number]) ? tab : tabs[0]
  const engineModels = (data?.models ?? []).filter((m) => m !== data?.book_reference)

  return (
    <PageShell>
      <div className="obs-root">
        <style>{PAGE_CSS}</style>
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Osservazione live</h1>
            <p className="mt-1 text-[15px]" style={{ color: TEXT_MUTED }}>
              Previsioni salvate prima del calcio d&apos;inizio e confrontate con gli esiti reali, modello per modello · nessuna giocata automatica
            </p>
          </div>
          <select className="pi-select" value={period} onChange={(e) => setPeriod(e.target.value as Period)} aria-label="Periodo">
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        {error && <p style={{ color: COLOR_NEG }}>{error}</p>}
        {!data && !error && <p style={{ color: TEXT_MUTED }}>Caricamento…</p>}

        {data && overview && (
          <div className="space-y-5">
            <Headline overview={overview} />

            <div className="grid gap-4 lg:grid-cols-3">
              {MODEL_ORDER.map((model) => (
                <ModelCard key={model} model={model} m={overview.models[model]} />
              ))}
            </div>

            <Section title="Profitto cumulato" note="Giocate chiuse, 1 unità per giocata">
              <CumulativeProfitChart overview={overview} />
            </Section>

            <Section title="Dettaglio per modello">
              {tabs.length === 0 ? (
                <p style={{ color: TEXT_MUTED }}>Nessuna previsione registrata nel periodo.</p>
              ) : (
                <>
                  <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Modello">
                    {tabs.map((m) => (
                      <button
                        key={m}
                        type="button"
                        role="tab"
                        aria-selected={m === current}
                        className="pi-btn"
                        style={{ borderColor: m === current ? MODEL_COLORS[m] : undefined, fontWeight: m === current ? 700 : 400 }}
                        onClick={() => setTab(m)}
                      >
                        <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: MODEL_COLORS[m] }} />
                        {m}
                      </button>
                    ))}
                  </div>
                  {current && <ModelDetail key={current} model={current} m={overview.models[current]} />}
                </>
              )}
            </Section>

            <Section title="V2.5 e V3 a confronto" note="Stessa partita e stesso mercato · giocate con quota da 1,50">
              <TallyTable
                rows={AGREEMENT_ROWS.map((r) => ({ key: r.key, label: r.label, ...(overview.agreement[r.key] as ObservationTally) }))}
                first="Quando"
                empty="Nessuna partita con entrambi i modelli."
              />
            </Section>

            <details className="pi-section">
              <summary className="pi-section-title cursor-pointer">Precisione delle previsioni (dato tecnico)</summary>
              <p className="mt-3 text-[15px]" style={{ color: TEXT_MUTED }}>
                Solo partite chiuse per tutti i modelli · errore = Brier medio (più basso = più preciso) · favorito = esito più probabile indovinato.
              </p>
              <div className="mt-3">
                {data.totals.common_fixtures === 0 ? (
                  <p style={{ color: TEXT_MUTED }}>Ancora nessuna partita chiusa per tutti i modelli nel periodo scelto.</p>
                ) : (
                  <EngineTable engines={data.engines} models={engineModels} />
                )}
              </div>
            </details>
          </div>
        )}
      </div>
    </PageShell>
  )
}
