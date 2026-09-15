import { useEffect, useMemo, useState } from 'react'
import { PageShell, Section } from '../components/layout/PageShell'
import {
  getObservationDashboard,
  groupLabel,
  type EngineMetrics,
  type IndexObservationBlock,
  type IndexObservationModel,
  type ObservationDashboard,
  type ObservationGroupStats,
} from '../lib/cecchinoLiveApi'
import { MARKET_LABELS } from '../lib/masterPatternApi'
import { formatFetchError } from '../utils/formatFetchError'

const TEXT_MUTED = 'var(--pi-muted)'
const COLOR_POS = 'var(--pi-pos)'
const COLOR_NEG = 'var(--pi-neg)'
const FAMILIES = ['1X2', 'Over/Under 2.5', 'Doppia chance', '1X2 primo tempo'] as const
const CHART_FAMILIES = ['1X2', 'Over/Under 2.5'] as const
/** Colori fissi per motore (mai riassegnati per posizione); il riferimento book resta grigio tratteggiato. */
const MODEL_COLORS: Record<string, string> = { V2: '#7c8cff', 'V2.5': '#35e0c4', V3: '#fbbf24' }
const BOOK_COLOR = '#8494b0'

type Period = '7' | '30' | '90' | 'all'
const PERIODS: { value: Period; label: string }[] = [
  { value: '7', label: 'Ultimi 7 giorni' },
  { value: '30', label: 'Ultimi 30 giorni' },
  { value: '90', label: 'Ultimi 90 giorni' },
  { value: 'all', label: 'Tutto il registro' },
]

function num(v: number | null | undefined, d = 1): string {
  return v == null ? '—' : v.toLocaleString('it-IT', { minimumFractionDigits: d, maximumFractionDigits: d })
}

function signed(v: number | null | undefined, d = 1, suffix = '%'): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${num(v, d)}${suffix}`
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

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="pi-kpi">
      <div className="text-[11px]" style={{ color: TEXT_MUTED }}>
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      {hint ? (
        <div className="mt-1 text-[11px]" style={{ color: TEXT_MUTED }}>
          {hint}
        </div>
      ) : null}
    </div>
  )
}

function EngineTable({ engines, models, book }: { engines: EngineMetrics; models: string[]; book: string }) {
  const rows = [...models, book]
  const bestBrier = (fam: string) => {
    const vals = models.map((m) => engines[m]?.[fam]?.brier).filter((v): v is number => v != null)
    return vals.length ? Math.min(...vals) : null
  }
  return (
    <div className="overflow-x-auto">
      <table className="pi-table min-w-[720px]">
        <thead>
          <tr>
            <th>Motore</th>
            {FAMILIES.map((f) => (
              <th key={f} className="text-right">
                {f}
                <div className="normal-case tracking-normal">errore · favorito</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => {
            const isBook = m === book
            return (
              <tr key={m}>
                <td className="whitespace-nowrap font-semibold">
                  <span
                    className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
                    style={{ background: isBook ? BOOK_COLOR : (MODEL_COLORS[m] ?? '#e8eef9') }}
                  />
                  {isBook ? `${book} (riferimento)` : m}
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
                  const best = !isBook && cell.brier != null && cell.brier === bestBrier(f)
                  return (
                    <td key={f} className="whitespace-nowrap text-right tabular-nums">
                      <span style={{ fontWeight: best ? 700 : 400 }}>{num(cell.brier, 4)}</span>
                      <span style={{ color: TEXT_MUTED }}> · {num(cell.favourite_hit_pct, 0)}%</span>
                      <div className="text-[10px]" style={{ color: TEXT_MUTED }}>
                        {cell.fixtures} partite
                      </div>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** Errore cumulato giorno per giorno: linee sottili, un solo asse, tooltip al passaggio. */
function CumulativeBrierChart({ data, models, book }: { data: ObservationDashboard['engines_daily']; models: string[]; book: string }) {
  const [family, setFamily] = useState<(typeof CHART_FAMILIES)[number]>('1X2')
  const [hover, setHover] = useState<number | null>(null)
  const series = [...models, book]
  const points = data.map((d) => ({
    date: d.scan_date,
    fixtures: d.cumulative_fixtures,
    values: Object.fromEntries(series.map((s) => [s, d.cumulative[s]?.[family]?.brier ?? null])) as Record<string, number | null>,
  }))
  const all = points.flatMap((p) => Object.values(p.values)).filter((v): v is number => v != null)
  if (points.length < 2 || all.length === 0) {
    return (
      <p className="text-sm" style={{ color: TEXT_MUTED }}>
        Il grafico compare dal secondo giorno con partite chiuse per tutti i motori.
      </p>
    )
  }
  const W = 720
  const H = 220
  const pad = { l: 48, r: 12, t: 10, b: 26 }
  const min = Math.min(...all)
  const max = Math.max(...all)
  const span = max - min || 0.01
  const lo = min - span * 0.15
  const hi = max + span * 0.15
  const x = (i: number) => pad.l + (i * (W - pad.l - pad.r)) / (points.length - 1)
  const y = (v: number) => pad.t + ((hi - v) * (H - pad.t - pad.b)) / (hi - lo)
  const ticks = [lo + (hi - lo) * 0.2, lo + (hi - lo) * 0.5, lo + (hi - lo) * 0.8]
  const hovered = hover != null ? points[hover] : null

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <select className="pi-select" value={family} onChange={(e) => setFamily(e.target.value as (typeof CHART_FAMILIES)[number])}>
          {CHART_FAMILIES.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        <div className="flex flex-wrap gap-3 text-[11px]" style={{ color: TEXT_MUTED }}>
          {series.map((s) => (
            <span key={s} className="inline-flex items-center gap-1.5">
              <svg width="18" height="6" aria-hidden>
                <line x1="0" y1="3" x2="18" y2="3" stroke={s === book ? BOOK_COLOR : MODEL_COLORS[s]} strokeWidth="2" strokeDasharray={s === book ? '4 3' : undefined} />
              </svg>
              {s === book ? `${book} (riferimento)` : s}
            </span>
          ))}
          <span>· errore più basso = più preciso</span>
        </div>
      </div>
      <div className="relative overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[520px]" role="img" aria-label={`Errore cumulato ${family} per motore`} onMouseLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="#1e2a44" strokeWidth="1" />
              <text x={pad.l - 6} y={y(t) + 3} textAnchor="end" fontSize="10" fill={BOOK_COLOR}>
                {t.toFixed(3)}
              </text>
            </g>
          ))}
          {points.map((p, i) => (
            <text key={p.date} x={x(i)} y={H - 8} textAnchor="middle" fontSize="10" fill={BOOK_COLOR}>
              {points.length <= 14 || i % Math.ceil(points.length / 14) === 0 ? shortDate(p.date) : ''}
            </text>
          ))}
          {series.map((s) => {
            const d = points
              .map((p, i) => (p.values[s] == null ? null : `${x(i)},${y(p.values[s] as number)}`))
              .filter(Boolean)
              .join(' L ')
            if (!d) return null
            return (
              <path
                key={s}
                d={`M ${d}`}
                fill="none"
                stroke={s === book ? BOOK_COLOR : MODEL_COLORS[s]}
                strokeWidth="2"
                strokeDasharray={s === book ? '5 4' : undefined}
                strokeLinejoin="round"
              />
            )
          })}
          {hover != null && <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={H - pad.b} stroke="#8494b0" strokeWidth="1" />}
          {hover != null &&
            series.map((s) =>
              points[hover].values[s] == null ? null : (
                <circle key={s} cx={x(hover)} cy={y(points[hover].values[s] as number)} r="4" fill={s === book ? BOOK_COLOR : MODEL_COLORS[s]} stroke="#0e1526" strokeWidth="2" />
              ),
            )}
          {points.map((p, i) => (
            <rect
              key={p.date}
              x={x(i) - (W - pad.l - pad.r) / (2 * (points.length - 1))}
              y={pad.t}
              width={(W - pad.l - pad.r) / (points.length - 1)}
              height={H - pad.t - pad.b}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            />
          ))}
        </svg>
        {hovered && (
          <div className="pi-tile pointer-events-none absolute right-2 top-2 text-[11px] tabular-nums">
            <div className="font-semibold">
              {shortDate(hovered.date)} · {hovered.fixtures} partite cumulate
            </div>
            {series.map((s) => (
              <div key={s} style={{ color: TEXT_MUTED }}>
                {s === book ? book : s}: <span style={{ color: 'var(--pi-text)' }}>{num(hovered.values[s], 4)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

const INDEX_PATTERN_ROWS: { key: keyof IndexObservationModel['by_pattern']; label: string }[] = [
  { key: 'confermate', label: 'Confermate da un pattern' },
  { key: 'in_contrasto', label: 'In contrasto con un pattern' },
  { key: 'altri_pattern', label: 'Pattern su altri mercati' },
  { key: 'senza_pattern', label: 'Nessun pattern acceso' },
]

function IndexRow({ label, b }: { label: string; b: IndexObservationBlock }) {
  return (
    <tr>
      <td>{label}</td>
      <td className="text-right tabular-nums">{b.predictions}</td>
      <td className="text-right tabular-nums">
        {b.won} · {b.lost}
        {b.pending ? <span style={{ color: TEXT_MUTED }}> · {b.pending} in attesa</span> : null}
      </td>
      <td className="text-right tabular-nums">{num(b.win_rate_pct)}</td>
      <td className="text-right tabular-nums">{b.playable_closed}</td>
      <td className="text-right tabular-nums" style={{ color: b.roi_pct == null ? undefined : b.roi_pct >= 0 ? COLOR_POS : COLOR_NEG }}>
        {signed(b.roi_pct)}
      </td>
    </tr>
  )
}

function IndexTable({ model }: { model: IndexObservationModel }) {
  return (
    <div className="pi-scroll" style={{ maxHeight: 'none' }}>
      <table className="pi-table">
        <thead>
          <tr>
            <th>Predizioni dell&apos;indice</th>
            <th className="text-right">Predizioni</th>
            <th className="text-right">Vinte · perse</th>
            <th className="text-right">% vinte</th>
            <th className="text-right">Giocabili con esito</th>
            <th className="text-right">ROI giocabili</th>
          </tr>
        </thead>
        <tbody>
          <IndexRow label="Tutte" b={model.all} />
          {INDEX_PATTERN_ROWS.map((r) => (
            <IndexRow key={r.key} label={r.label} b={model.by_pattern[r.key]} />
          ))}
          {Object.entries(model.by_score).map(([label, b]) => (
            <IndexRow key={label} label={`Punteggio ${label}`} b={b} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function GroupTable({ groups }: { groups: ObservationGroupStats[] }) {
  const [kind, setKind] = useState<'all' | 'market' | 'synthetic'>('all')
  const [onlyClosed, setOnlyClosed] = useState(false)
  const shown = groups.filter((g) => (kind === 'all' || g.target_type === kind) && (!onlyClosed || g.won + g.lost > 0))
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select className="pi-select" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          <option value="all">Tutti i mercati</option>
          <option value="market">Con quota</option>
          <option value="synthetic">Senza quota (tiri, corner, cartellini)</option>
        </select>
        <label className="inline-flex items-center gap-2 text-xs" style={{ color: TEXT_MUTED }}>
          <input type="checkbox" checked={onlyClosed} onChange={(e) => setOnlyClosed(e.target.checked)} />
          Solo con esiti
        </label>
        <span className="text-[11px]" style={{ color: TEXT_MUTED }}>
          {shown.length} mercati
        </span>
      </div>
      {shown.length === 0 ? (
        <p className="text-sm" style={{ color: TEXT_MUTED }}>
          Nessun pattern acceso nel periodo scelto.
        </p>
      ) : (
        <div className="pi-scroll">
          <table className="pi-table min-w-[860px]">
            <thead>
              <tr>
                <th>Mercato</th>
                <th>Motore</th>
                <th className="text-right">Segnali</th>
                <th className="text-right">Vinti · persi</th>
                <th className="text-right">In attesa</th>
                <th className="text-right">% live</th>
                <th className="text-right">% storico</th>
                <th className="text-right">ROI live</th>
                <th className="text-right">Quota media</th>
                <th className="text-right">Pattern concordi</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((g) => {
                const diff = g.win_rate_pct != null && g.hist_win_rate_pct != null ? g.win_rate_pct - g.hist_win_rate_pct : null
                return (
                  <tr key={`${g.model}-${g.key}`}>
                    <td className="font-medium">
                      {groupLabel(g, MARKET_LABELS)}
                      <div className="text-[10px]" style={{ color: TEXT_MUTED }}>
                        {g.target_type === 'market' ? 'con quota' : 'senza quota'}
                      </div>
                    </td>
                    <td>{g.model}</td>
                    <td className="text-right tabular-nums">{g.signals}</td>
                    <td className="whitespace-nowrap text-right tabular-nums">
                      {g.won} · {g.lost}
                    </td>
                    <td className="text-right tabular-nums" style={{ color: TEXT_MUTED }}>
                      {g.pending}
                    </td>
                    <td className="text-right tabular-nums">
                      {num(g.win_rate_pct)}
                      {diff != null && (
                        <div className="text-[10px]" style={{ color: diff >= 0 ? COLOR_POS : COLOR_NEG }}>
                          {signed(diff, 1, ' pt')}
                        </div>
                      )}
                    </td>
                    <td className="text-right tabular-nums" style={{ color: TEXT_MUTED }}>
                      {num(g.hist_win_rate_pct)}
                    </td>
                    <td className="text-right tabular-nums" style={{ color: g.roi_pct == null ? TEXT_MUTED : g.roi_pct >= 0 ? COLOR_POS : COLOR_NEG }}>
                      {g.target_type === 'market' ? signed(g.roi_pct) : '—'}
                    </td>
                    <td className="text-right tabular-nums">{g.target_type === 'market' ? num(g.avg_quota, 2) : '—'}</td>
                    <td className="text-right tabular-nums">{num(g.avg_patterns, 1)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function LiveObservationPage() {
  const [period, setPeriod] = useState<Period>('30')
  const [data, setData] = useState<ObservationDashboard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showPatterns, setShowPatterns] = useState(false)

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

  const winPct = useMemo(() => {
    if (!data) return null
    const won = data.pattern_groups.reduce((a, g) => a + g.won, 0)
    const closed = data.totals.signals_closed
    return closed ? (100 * won) / closed : null
  }, [data])

  return (
    <PageShell>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Osservazione live</h1>
          <p className="mt-1 text-xs" style={{ color: TEXT_MUTED }}>
            Previsioni congelate prima del calcio d&apos;inizio e confrontate con gli esiti reali · nessuna giocata automatica
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

      {error && <p className="text-sm" style={{ color: COLOR_NEG }}>{error}</p>}
      {!data && !error && (
        <p className="text-sm" style={{ color: TEXT_MUTED }}>
          Caricamento…
        </p>
      )}

      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Partite registrate" value={String(data.totals.fixtures)} hint={data.models.map((m) => `${m} ${data.totals.predictions_by_model[m] ?? 0}`).join(' · ') || undefined} />
            <Kpi label="Partite chiuse" value={String(data.totals.fixtures_settled)} hint={`${data.totals.common_fixtures} chiuse per tutti i motori`} />
            <Kpi label="Segnali pattern" value={String(data.totals.signals)} hint={`${data.totals.signals_closed} con esito · un segnale = un mercato su una partita`} />
            <Kpi label="Segnali vinti" value={winPct == null ? '—' : `${num(winPct)}%`} hint="sui segnali con esito" />
          </div>

          <Section title="Motori" note="Solo partite chiuse per tutti i motori · errore = Brier medio per selezione · favorito = esito più probabile indovinato">
            {data.totals.common_fixtures === 0 ? (
              <p className="text-sm" style={{ color: TEXT_MUTED }}>
                Ancora nessuna partita chiusa per tutti i motori nel periodo scelto.
              </p>
            ) : (
              <div className="space-y-4">
                <EngineTable engines={data.engines} models={data.models} book={data.book_reference} />
                <CumulativeBrierChart data={data.engines_daily} models={data.models} book={data.book_reference} />
                {data.engines_base && data.engines_base.fixtures > 0 && (
                  <div>
                    <p className="mb-2 text-[11px]" style={{ color: TEXT_MUTED }}>
                      {data.engines_base.models.join(' e ')} su tutte le loro partite chiuse ({data.engines_base.fixtures}): la V3 c&apos;è solo nei campionati con statistiche.
                    </p>
                    <EngineTable engines={data.engines_base.engines} models={data.engines_base.models} book={data.book_reference} />
                  </div>
                )}
              </div>
            )}
          </Section>

          <Section
            title="Indice di Acquistabilità: predizioni e conferma dei pattern"
            note="Predizioni da 70/100 in su registrate prima della partita · giocabili = quota Bet365 da 1,50 · contano solo i pattern costruiti sui moduli"
          >
            {Object.keys(data.purchasability_index ?? {}).length === 0 ? (
              <p className="text-sm" style={{ color: TEXT_MUTED }}>
                Nessuna predizione dell&apos;indice registrata nel periodo: le prime arrivano con la prossima scansione.
              </p>
            ) : (
              <div className="space-y-4">
                {Object.entries(data.purchasability_index ?? {}).map(([model, m]) => (
                  <div key={model}>
                    <div className="mb-2 text-xs font-semibold" style={{ color: MODEL_COLORS[model] ?? TEXT_MUTED }}>
                      {model} · {m.fixtures} partite
                    </div>
                    <IndexTable model={m} />
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="Pattern Master per mercato" note="Pattern accesi sullo stesso mercato, linea e direzione contano come un solo segnale per partita">
            <GroupTable groups={data.pattern_groups} />
          </Section>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Section title="Più pattern concordi, più affidabile?" note="Esito dei segnali per numero di pattern accesi insieme">
              <table className="pi-table">
                <thead>
                  <tr>
                    <th>Pattern concordi</th>
                    <th className="text-right">Segnali con esito</th>
                    <th className="text-right">Vinti · persi</th>
                    <th className="text-right">% vinti</th>
                  </tr>
                </thead>
                <tbody>
                  {data.concordance.map((b) => (
                    <tr key={b.band}>
                      <td>{b.band}</td>
                      <td className="text-right tabular-nums">{b.signals}</td>
                      <td className="text-right tabular-nums">
                        {b.won} · {b.lost}
                      </td>
                      <td className="text-right tabular-nums">{num(b.win_rate_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>

            <Section title="Giornata per giornata">
              {data.days.length === 0 ? (
                <p className="text-sm" style={{ color: TEXT_MUTED }}>
                  Nessuna giornata registrata nel periodo.
                </p>
              ) : (
                <div className="pi-scroll">
                  <table className="pi-table">
                    <thead>
                      <tr>
                        <th>Giornata</th>
                        <th className="text-right">Partite · chiuse</th>
                        <th className="text-right">Segnali</th>
                        <th className="text-right">Vinti · persi</th>
                        <th className="text-right">In attesa</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.days.map((d) => (
                        <tr key={d.scan_date}>
                          <td className="whitespace-nowrap">{new Date(`${d.scan_date}T12:00:00`).toLocaleDateString('it-IT', { weekday: 'short', day: '2-digit', month: '2-digit' })}</td>
                          <td className="text-right tabular-nums">
                            {d.fixtures} · {d.fixtures_settled}
                          </td>
                          <td className="text-right tabular-nums">
                            {d.groups_active}
                            <div className="text-[10px]" style={{ color: TEXT_MUTED }}>
                              {d.patterns_active} pattern
                            </div>
                          </td>
                          <td className="text-right tabular-nums">
                            {d.groups_won} · {d.groups_lost}
                          </td>
                          <td className="text-right tabular-nums" style={{ color: TEXT_MUTED }}>
                            {d.groups_pending}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Section>
          </div>

          <Section
            title="Singoli pattern"
            note={
              <button type="button" className="pi-btn" onClick={() => setShowPatterns((s) => !s)}>
                {showPatterns ? 'Nascondi' : `Mostra (${data.patterns_total})`}
              </button>
            }
          >
            {showPatterns ? (
              data.patterns.length === 0 ? (
                <p className="text-sm" style={{ color: TEXT_MUTED }}>
                  Nessun pattern acceso nel periodo scelto.
                </p>
              ) : (
                <div className="pi-scroll">
                  <table className="pi-table min-w-[900px]">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Mercato</th>
                        <th>Condizioni</th>
                        <th className="text-right">Segnali</th>
                        <th className="text-right">Vinti · persi</th>
                        <th className="text-right">% live · storico</th>
                        <th className="text-right">ROI live · storico</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.patterns.map((p) => (
                        <tr key={`${p.model}-${p.id}`}>
                          <td className="tabular-nums" style={{ color: TEXT_MUTED }}>
                            {p.id}
                          </td>
                          <td className="whitespace-nowrap font-medium">{groupLabel(p, MARKET_LABELS)}</td>
                          <td className="text-[11px]" style={{ color: TEXT_MUTED }}>
                            {p.conditions_text}
                          </td>
                          <td className="text-right tabular-nums">{p.signals}</td>
                          <td className="whitespace-nowrap text-right tabular-nums">
                            {p.won} · {p.lost}
                          </td>
                          <td className="whitespace-nowrap text-right tabular-nums">
                            {num(p.win_rate_pct)} <span style={{ color: TEXT_MUTED }}>· {num(p.hist_win_rate_pct)}</span>
                          </td>
                          <td className="whitespace-nowrap text-right tabular-nums">
                            {p.target_type === 'market' ? (
                              <>
                                {signed(p.roi_pct)} <span style={{ color: TEXT_MUTED }}>· {signed(p.hist_roi_pct)}</span>
                              </>
                            ) : (
                              <span style={{ color: TEXT_MUTED }}>scarto storico {signed(p.hist_deviation_pct, 1, ' pt')}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            ) : (
              <p className="text-xs" style={{ color: TEXT_MUTED }}>
                Dettaglio pattern per pattern, ordinato per numero di esiti.
              </p>
            )}
          </Section>
        </div>
      )}
    </PageShell>
  )
}
