import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Section, heatBg } from './PatternInsightsShell'
import type {
  PatternInsightTargetType,
  ValidationAnalytics,
  ValidationRate,
} from '../../lib/patternInsightsApi'

// Coppie validate con dataviz/validate_palette.js sul fondo #0e1526 (tutti i
// controlli PASS, incluso daltonismo): stagione di scoperta vs verifica, e
// sopra vs sotto il livello del caso.
export const SEASON_DISCOVERY = '#8a78e6'
export const SEASON_VALIDATION = '#1ea68f'
export const ABOVE_CHANCE = '#1ea68f'
export const BELOW_CHANCE = '#d95a57'
const CHANCE_LINE = '#8494b0'

const AXIS = { fill: '#8494b0', fontSize: 11 }
const GRID = '#1e2a44'
const TOOLTIP_STYLE = {
  background: '#131c31',
  border: '1px solid #1e2a44',
  borderRadius: 10,
  color: '#e8eef9',
  fontSize: 12,
}

const TYPE_LABEL: Record<PatternInsightTargetType, string> = {
  market: 'Mercati con quota',
  synthetic: 'Situazioni senza quota',
}

function pct(v: number | null | undefined, d = 1): string {
  if (v == null) return '—'
  return `${v.toFixed(d)}%`
}

function signedPct(v: number | null | undefined, d = 1): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(d)}%`
}

function liftText(lift: number | null | undefined): string {
  return lift == null ? '—' : `${lift.toFixed(2)}×`
}

/** Lettura automatica del lift: dipende solo dai numeri, cosi' resta valida
 * anche per le stagioni di verifica successive. */
function liftVerdict(lift: number | null | undefined): { text: string; tone: string } {
  if (lift == null) return { text: 'Dati insufficienti', tone: 'var(--pi-muted)' }
  if (lift >= 2) return { text: 'Segnale forte, ben oltre il caso', tone: ABOVE_CHANCE }
  if (lift >= 1.25) return { text: 'Segnale moderato sopra il caso', tone: ABOVE_CHANCE }
  if (lift > 0.9) return { text: 'Indistinguibile dal caso', tone: 'var(--pi-warn)' }
  return { text: 'Peggio del caso', tone: BELOW_CHANCE }
}

function HeroComparison({
  kind,
  rate,
  season,
}: {
  kind: PatternInsightTargetType
  rate: ValidationRate
  season: string
}) {
  const verdict = liftVerdict(rate.lift)
  const observed = rate.confirmed_rate_pct ?? 0
  const expected = rate.expected_rate_pct ?? 0
  return (
    <div className="pi-kpi" style={{ padding: 18 }}>
      <div
        className="text-[10px] font-semibold uppercase tracking-wider"
        style={{ color: 'var(--pi-muted)' }}
      >
        {TYPE_LABEL[kind]}
      </div>

      <div className="mt-2 flex flex-wrap items-end gap-x-6 gap-y-2">
        <div>
          <div className="text-4xl font-bold tabular-nums">{pct(observed)}</div>
          <div className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            riconfermati nel {season}
          </div>
        </div>
        <div>
          <div className="text-2xl font-semibold tabular-nums" style={{ color: 'var(--pi-muted)' }}>
            {pct(expected)}
          </div>
          <div className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            attesi per puro caso
          </div>
        </div>
        <div>
          <div className="text-2xl font-semibold tabular-nums">{liftText(rate.lift)}</div>
          <div className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            rispetto al caso
          </div>
        </div>
      </div>

      <div className="relative mt-4 h-3 w-full rounded-full" style={{ background: '#1a2438' }}>
        <div
          className="h-3 rounded-full"
          style={{ width: `${Math.min(100, observed)}%`, background: rate.lift != null && rate.lift >= 1.25 ? ABOVE_CHANCE : 'var(--pi-warn)' }}
        />
        <div
          className="absolute top-[-4px] h-5 w-[2px]"
          style={{ left: `${Math.min(100, expected)}%`, background: '#e8eef9' }}
          title="Livello atteso per caso"
        />
      </div>
      <div className="mt-1 text-[10px]" style={{ color: 'var(--pi-muted)' }}>
        La barra e&apos; la quota riconfermata, la tacca bianca e&apos; il livello del caso.
      </div>

      <div className="mt-3 text-sm font-semibold" style={{ color: verdict.tone }}>
        {verdict.text}
      </div>
      <div className="mt-2 grid grid-cols-4 gap-2 text-[11px]">
        {[
          ['Testati', rate.tested],
          ['Confermati', rate.confirmed],
          [kind === 'synthetic' ? 'Attenuati' : 'Respinti', kind === 'synthetic' ? rate.attenuated : rate.rejected],
          ['Camp. insuff.', rate.insufficient],
        ].map(([label, value]) => (
          <div key={String(label)}>
            <div style={{ color: 'var(--pi-muted)' }}>{label}</div>
            <div className="tabular-nums font-semibold">{Number(value).toLocaleString('it-IT')}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ValidationHeadlineBlock({ data }: { data: ValidationAnalytics }) {
  const season = data.validation?.season_label ?? 'stagione di verifica'
  const parity = data.validation?.summary
  return (
    <Section
      title={`Verifica fuori campione · ${season}`}
      note="I pattern trovati nella stagione di scoperta, misurati su una stagione mai vista"
    >
      <p className="mb-3 max-w-4xl text-xs leading-relaxed" style={{ color: 'var(--pi-muted)' }}>
        Un pattern e&apos; <strong style={{ color: 'var(--pi-text)' }}>confermato</strong> se nella
        nuova stagione ha ancora ROI positivo (mercati) o sposta ancora la frequenza nella stessa
        direzione di almeno 5 punti (situazioni). Il confronto decisivo e&apos; con il{' '}
        <strong style={{ color: 'var(--pi-text)' }}>livello del caso</strong>: quanti pattern avrebbero
        passato lo stesso criterio scegliendo a caso lo stesso numero di partite.
      </p>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {data.headline?.market && (
          <HeroComparison kind="market" rate={data.headline.market} season={season} />
        )}
        {data.headline?.synthetic && (
          <HeroComparison kind="synthetic" rate={data.headline.synthetic} season={season} />
        )}
      </div>

      {parity?.parity_checked != null && (
        <div
          className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-[11px]"
          style={{
            borderColor: parity.parity_mismatches === 0 ? 'rgba(30,166,143,0.4)' : 'rgba(217,90,87,0.5)',
            background: parity.parity_mismatches === 0 ? 'rgba(30,166,143,0.07)' : 'rgba(217,90,87,0.08)',
            color: 'var(--pi-muted)',
          }}
        >
          <span className="pi-chip">
            {parity.parity_mismatches === 0 ? '✓' : '!'} Controllo di parita&apos;
          </span>
          <span>
            {parity.parity_checked.toLocaleString('it-IT')} pattern ricalcolati sulla stagione di
            scoperta prima della verifica:{' '}
            <strong style={{ color: 'var(--pi-text)' }}>
              {parity.parity_mismatches} discrepanze
            </strong>
            . La nuova stagione viene misurata con esattamente la stessa definizione dei pattern.
          </span>
        </div>
      )}
    </Section>
  )
}

function RateByBucketChart({
  rows,
  title,
}: {
  rows: Array<ValidationRate & { bucket: string }>
  title: string
}) {
  const data = rows.map((r) => ({
    bucket: r.bucket,
    observed: r.confirmed_rate_pct ?? 0,
    expected: r.expected_rate_pct ?? 0,
    lift: r.lift,
    tested: r.tested,
  }))
  return (
    <div className="pi-tile">
      <div className="mb-1 text-xs font-semibold">{title}</div>
      <ResponsiveContainer width="100%" height={250}>
        <ComposedChart data={data} margin={{ left: -8, right: 12, top: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
          <XAxis dataKey="bucket" tick={AXIS} stroke={GRID} />
          <YAxis unit="%" tick={AXIS} stroke={GRID} domain={[0, 100]} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: 'rgba(30,166,143,0.06)' }}
            formatter={(v, name) => [
              `${Number(v).toFixed(1)}%`,
              name === 'observed' ? 'Riconfermati' : 'Attesi per caso',
            ]}
            labelFormatter={(l) => `Campione ${l} partite`}
          />
          <Legend
            formatter={(v) => (v === 'observed' ? 'Riconfermati' : 'Attesi per caso')}
            wrapperStyle={{ fontSize: 11, color: '#8494b0' }}
          />
          <Bar dataKey="observed" fill={SEASON_VALIDATION} radius={[4, 4, 0, 0]} maxBarSize={48} />
          <Line
            dataKey="expected"
            stroke={CHANCE_LINE}
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={{ r: 4, fill: CHANCE_LINE }}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {data.map((d) => (
          <span key={d.bucket} className="rounded px-1.5 py-0.5 text-[10px] tabular-nums" style={{ background: '#1a2438' }}>
            {d.bucket}: {liftText(d.lift)}
          </span>
        ))}
      </div>
    </div>
  )
}

export function SampleProofBlock({ data }: { data: ValidationAnalytics }) {
  const byType = (t: PatternInsightTargetType) => (data.by_bucket ?? []).filter((r) => r.target_type === t)
  const complexity = data.by_complexity ?? []
  return (
    <Section
      title="La prova del campione"
      note="Un effetto reale si conferma di piu' quando il campione cresce; il rumore no"
    >
      <p className="mb-3 max-w-4xl text-xs leading-relaxed" style={{ color: 'var(--pi-muted)' }}>
        Fasce costruite sul campione della stagione di scoperta. Se la barra sale man mano che il
        campione cresce e si stacca dalla linea tratteggiata, il pattern cattura qualcosa di vero. Se
        resta incollata alla linea a ogni fascia, il campione piu&apos; grande non aggiunge nulla: era
        rumore.
      </p>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <RateByBucketChart rows={byType('market')} title="Mercati con quota" />
        <RateByBucketChart rows={byType('synthetic')} title="Situazioni senza quota" />
      </div>

      {complexity.length > 0 && (
        <div className="mt-3">
          <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Stessa lettura per numero di condizioni combinate nel pattern.
          </div>
          <div className="pi-scroll" style={{ maxHeight: 260 }}>
            <table className="pi-table">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Condizioni</th>
                  <th>Testati</th>
                  <th>Riconfermati</th>
                  <th>Attesi per caso</th>
                  <th>Rispetto al caso</th>
                </tr>
              </thead>
              <tbody>
                {complexity.map((r) => (
                  <tr key={`${r.target_type}-${r.atoms}`}>
                    <td className="font-semibold">{TYPE_LABEL[r.target_type]}</td>
                    <td className="tabular-nums">{r.atoms}</td>
                    <td className="tabular-nums">{r.tested.toLocaleString('it-IT')}</td>
                    <td className="tabular-nums">{pct(r.confirmed_rate_pct)}</td>
                    <td className="tabular-nums" style={{ color: 'var(--pi-muted)' }}>
                      {pct(r.expected_rate_pct)}
                    </td>
                    <td className="tabular-nums font-semibold">{liftText(r.lift)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Section>
  )
}

export function ShrinkageBlock({ data }: { data: ValidationAnalytics }) {
  const season = data.validation?.season_label ?? 'verifica'
  const rows = (data.shrinkage ?? []).map((r) => ({
    bucket: r.bucket,
    disc: r.disc_avg_roi_pct ?? 0,
    oos: r.oos_avg_roi_pct ?? 0,
    patterns: r.patterns,
  }))
  const scatter = data.scatter ?? []
  const confirmed = scatter.filter((p) => p.verdict === 'confirmed')
  const rejected = scatter.filter((p) => p.verdict !== 'confirmed')

  return (
    <Section
      title="Il ROI della scoperta regge?"
      note="ROI medio dei pattern di mercato, raggruppati per quanto rendevano in scoperta"
    >
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="pi-tile">
          <div className="mb-1 text-xs font-semibold">ROI in scoperta vs ROI nella nuova stagione</div>
          <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Se il ROI trovato fosse vantaggio reale, le barre della verifica seguirebbero quelle della
            scoperta. Se crollano tutte allo stesso livello negativo, quel ROI era rumore e resta solo
            il margine del bookmaker.
          </div>
          <ResponsiveContainer width="100%" height={270}>
            <BarChart data={rows} margin={{ left: -8, right: 12, top: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <XAxis dataKey="bucket" tick={AXIS} stroke={GRID} />
              <YAxis unit="%" tick={AXIS} stroke={GRID} />
              <ReferenceLine y={0} stroke="#3a5573" />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                cursor={{ fill: 'rgba(138,120,230,0.06)' }}
                formatter={(v, name) => [
                  signedPct(Number(v)),
                  name === 'disc' ? 'ROI medio in scoperta' : `ROI medio ${season}`,
                ]}
                labelFormatter={(l) => `ROI in scoperta ${l}`}
              />
              <Legend
                formatter={(v) => (v === 'disc' ? 'Scoperta' : season)}
                wrapperStyle={{ fontSize: 11, color: '#8494b0' }}
              />
              <Bar dataKey="disc" fill={SEASON_DISCOVERY} radius={[4, 4, 0, 0]} maxBarSize={36} />
              <Bar dataKey="oos" fill={SEASON_VALIDATION} radius={[4, 4, 0, 0]} maxBarSize={36} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="pi-tile">
          <div className="mb-1 text-xs font-semibold">Pattern per pattern (campione)</div>
          <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Ogni punto e&apos; un pattern: in orizzontale il ROI in scoperta, in verticale quello nella
            nuova stagione. Una nuvola piatta intorno allo zero significa che il primo non predice il
            secondo.
          </div>
          <ResponsiveContainer width="100%" height={270}>
            <ScatterChart margin={{ left: -8, right: 12, top: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
              <XAxis type="number" dataKey="disc_roi_pct" name="ROI scoperta" unit="%" tick={AXIS} stroke={GRID} />
              <YAxis type="number" dataKey="oos_roi_pct" name={`ROI ${season}`} unit="%" tick={AXIS} stroke={GRID} />
              <ReferenceLine y={0} stroke="#3a5573" />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                cursor={{ strokeDasharray: '3 3', stroke: '#8494b0' }}
                formatter={(v, name) => [signedPct(Number(v)), name]}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: '#8494b0' }} />
              <Scatter name="Confermati" data={confirmed} fill={ABOVE_CHANCE} fillOpacity={0.7} />
              <Scatter name="Respinti" data={rejected} fill={BELOW_CHANCE} fillOpacity={0.45} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>
    </Section>
  )
}

function LiftBars({
  rows,
  height,
  labelWidth,
}: {
  rows: Array<{ label: string; lift: number }>
  height: number
  labelWidth: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 30 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} stroke={GRID} tickFormatter={(v) => `${v}×`} />
        <YAxis type="category" dataKey="label" width={labelWidth} tick={AXIS} stroke={GRID} />
        <ReferenceLine
          x={1}
          stroke="#e8eef9"
          strokeDasharray="4 3"
          label={{ value: 'caso', fill: '#8494b0', fontSize: 10, position: 'top' }}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ fill: 'rgba(30,166,143,0.06)' }}
          formatter={(v) => [`${Number(v).toFixed(2)}× rispetto al caso`, 'Riconferma']}
        />
        <Bar dataKey="lift" radius={[0, 4, 4, 0]} maxBarSize={18}>
          {rows.map((r) => (
            <Cell key={r.label} fill={r.lift >= 1 ? ABOVE_CHANCE : BELOW_CHANCE} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function MarketValidationBlock({ data }: { data: ValidationAnalytics }) {
  const season = data.validation?.season_label ?? 'verifica'
  const markets = useMemo(
    () =>
      (data.by_target ?? [])
        .filter((r) => r.target_type === 'market' && r.lift != null)
        .sort((a, b) => (b.lift ?? 0) - (a.lift ?? 0)),
    [data.by_target],
  )
  const maxLift = Math.max(1.5, ...markets.map((m) => m.lift ?? 0))

  return (
    <Section title="Mercato per mercato" note="Quali mercati si riconfermano sopra il caso">
      <div className="grid grid-cols-1 gap-3 2xl:grid-cols-[1fr_1.3fr]">
        <div className="pi-tile">
          <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            A destra della linea tratteggiata il mercato si riconferma piu&apos; spesso del caso, a
            sinistra meno.
          </div>
          <LiftBars
            rows={markets.map((m) => ({ label: m.target_label, lift: m.lift ?? 0 }))}
            height={Math.max(300, markets.length * 24)}
            labelWidth={140}
          />
        </div>
        <div className="pi-scroll">
          <table className="pi-table">
            <thead>
              <tr>
                <th>Mercato</th>
                <th>Testati</th>
                <th>Riconfermati</th>
                <th>Attesi</th>
                <th>Rispetto al caso</th>
                <th>ROI medio scoperta</th>
                <th>ROI medio {season}</th>
              </tr>
            </thead>
            <tbody>
              {markets.map((m) => (
                <tr key={m.target_key}>
                  <td className="font-semibold">{m.target_label}</td>
                  <td className="tabular-nums">{m.tested.toLocaleString('it-IT')}</td>
                  <td className="tabular-nums">{pct(m.confirmed_rate_pct)}</td>
                  <td className="tabular-nums" style={{ color: 'var(--pi-muted)' }}>
                    {pct(m.expected_rate_pct)}
                  </td>
                  <td
                    className="tabular-nums font-semibold"
                    style={{ background: heatBg((m.lift ?? 1) - 1, maxLift - 1, (m.lift ?? 1) >= 1) }}
                  >
                    {liftText(m.lift)}
                  </td>
                  <td className="tabular-nums">{signedPct(m.disc_avg_roi_pct)}</td>
                  <td
                    className="tabular-nums font-semibold"
                    style={{ color: (m.oos_avg_roi_pct ?? 0) >= 0 ? 'var(--pi-text)' : BELOW_CHANCE }}
                  >
                    {signedPct(m.oos_avg_roi_pct)}
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

function familyOf(label: string): string {
  if (label.includes('in porta')) return 'Tiri in porta'
  if (label.includes('Corner')) return 'Corner'
  if (label.includes('Cartellini')) return 'Cartellini'
  return 'Tiri'
}

export function SituationValidationBlock({ data }: { data: ValidationAnalytics }) {
  const situations = useMemo(
    () =>
      (data.by_target ?? [])
        .filter((r) => r.target_type === 'synthetic' && r.tested > 0)
        .sort((a, b) => (b.lift ?? 0) - (a.lift ?? 0)),
    [data.by_target],
  )

  const families = useMemo(() => {
    const acc: Record<string, { tested: number; confirmed: number; expected: number }> = {}
    for (const s of situations) {
      const f = familyOf(s.target_label)
      acc[f] ??= { tested: 0, confirmed: 0, expected: 0 }
      acc[f].tested += s.tested
      acc[f].confirmed += s.confirmed
      acc[f].expected += ((s.expected_rate_pct ?? 0) / 100) * s.tested
    }
    return Object.entries(acc)
      .map(([name, v]) => ({
        name,
        tested: v.tested,
        confirmedRate: v.tested ? (v.confirmed / v.tested) * 100 : null,
        expectedRate: v.tested ? (v.expected / v.tested) * 100 : null,
        lift: v.expected > 0 ? v.confirmed / v.expected : null,
      }))
      .sort((a, b) => (b.lift ?? 0) - (a.lift ?? 0))
  }, [situations])

  const maxLift = Math.max(2, ...situations.map((s) => s.lift ?? 0))

  return (
    <Section
      title="Situazioni di gioco: cosa resta prevedibile"
      note="Tiri, tiri in porta, corner e cartellini: statistiche di frequenza, senza quota storica"
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {families.map((f) => {
          const v = liftVerdict(f.lift)
          return (
            <div key={f.name} className="pi-kpi">
              <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--pi-muted)' }}>
                {f.name}
              </div>
              <div className="mt-1 text-2xl font-bold tabular-nums">{pct(f.confirmedRate)}</div>
              <div className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
                riconfermati · caso {pct(f.expectedRate)}
              </div>
              <div className="mt-1 text-xs font-semibold" style={{ color: v.tone }}>
                {liftText(f.lift)} · {v.text}
              </div>
            </div>
          )
        })}
      </div>

      <div className="mt-3 pi-scroll" style={{ maxHeight: 480 }}>
        <table className="pi-table">
          <thead>
            <tr>
              <th>Situazione</th>
              <th>Famiglia</th>
              <th>Testati</th>
              <th>Riconfermati</th>
              <th>Attenuati</th>
              <th>Respinti</th>
              <th>Attesi per caso</th>
              <th>Rispetto al caso</th>
            </tr>
          </thead>
          <tbody>
            {situations.map((s) => (
              <tr key={`${s.target_key}-${s.target_label}`} style={{ opacity: s.tested < 30 ? 0.5 : 1 }}>
                <td className="font-semibold">
                  {s.target_label}
                  {s.tested < 30 && (
                    <span className="ml-1 text-[10px]" style={{ color: 'var(--pi-muted)' }}>
                      (pochi pattern)
                    </span>
                  )}
                </td>
                <td style={{ color: 'var(--pi-muted)' }}>{familyOf(s.target_label)}</td>
                <td className="tabular-nums">{s.tested.toLocaleString('it-IT')}</td>
                <td className="tabular-nums font-semibold">{pct(s.confirmed_rate_pct)}</td>
                <td className="tabular-nums">{s.attenuated.toLocaleString('it-IT')}</td>
                <td className="tabular-nums">{s.rejected.toLocaleString('it-IT')}</td>
                <td className="tabular-nums" style={{ color: 'var(--pi-muted)' }}>
                  {pct(s.expected_rate_pct)}
                </td>
                <td
                  className="tabular-nums font-semibold"
                  style={{ background: heatBg((s.lift ?? 1) - 1, maxLift - 1, (s.lift ?? 1) >= 1) }}
                >
                  {liftText(s.lift)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}
