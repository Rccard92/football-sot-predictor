import { useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Section } from './PatternInsightsShell'
import { ABOVE_CHANCE, BELOW_CHANCE, SEASON_DISCOVERY, SEASON_VALIDATION } from './PatternValidationBlocks'
import type { MarketScoreboard, TierKey } from '../../lib/patternInsightsApi'

const BOOK_LINE = '#8494b0'
const AXIS = { fill: '#8494b0', fontSize: 11 }
const GRID = '#1e2a44'
const TOOLTIP_STYLE = {
  background: '#131c31',
  border: '1px solid #1e2a44',
  borderRadius: 10,
  color: '#e8eef9',
  fontSize: 12,
}

const FAMILY_LABEL: Record<string, string> = {
  FT_1X2: '1X2 finale',
  DOUBLE_CHANCE: 'Doppia chance',
  FT_OVER_UNDER: 'Over/Under',
  HT_1X2: '1X2 primo tempo',
}

const BUCKET_LABEL: Record<string, string> = {
  '<-20': 'meno di -20%',
  '-20..-10': '-20 / -10%',
  '-10..0': '-10 / 0%',
  '0..10': '0 / +10%',
  '10..20': '+10 / +20%',
  '20..40': '+20 / +40%',
  '40+': 'oltre +40%',
}

function signedPct(v: number | null | undefined, d = 1): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(d)}%`
}

/** Di quanto l'errore di Cecchino supera quello del bookmaker (Brier, in %). */
function gapPct(c: number | null, b: number | null): number | null {
  if (c == null || b == null || b === 0) return null
  return ((c - b) / b) * 100
}

function Toggle<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<{ key: T; label: string }>
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          className="pi-btn"
          style={o.key === value ? { borderColor: 'var(--pi-accent)', color: 'var(--pi-accent)' } : undefined}
          onClick={() => onChange(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function MarketScoreboardBlock({ data }: { data: MarketScoreboard }) {
  const [tier, setTier] = useState<TierKey>('all')
  const [season, setSeason] = useState<string>(data.seasons[data.seasons.length - 1] ?? '')

  const accuracyRows = useMemo(() => {
    const families = Object.keys(FAMILY_LABEL)
    return families.map((f) => {
      const row: Record<string, number | string | null> = { family: FAMILY_LABEL[f] }
      for (const s of data.seasons) {
        const a = data.accuracy.find((x) => x.market_family === f && x.season_label === s && x.tier === tier)
        row[s] = a ? gapPct(a.brier_cecchino, a.brier_book) : null
        row[`${s}__c`] = a?.brier_cecchino ?? null
        row[`${s}__b`] = a?.brier_book ?? null
      }
      return row
    })
  }, [data, tier])

  const seasonGap = useMemo(
    () =>
      accuracyRows.map((r) => ({
        family: String(r.family),
        gap: Number(r[season] ?? 0),
      })),
    [accuracyRows, season],
  )

  const curve = useMemo(
    () =>
      data.value_curve
        .filter((v) => v.season_label === season && v.tier === tier)
        .map((v) => ({ ...v, label: BUCKET_LABEL[v.bucket] ?? v.bucket })),
    [data.value_curve, season, tier],
  )

  const competitions = useMemo(
    () => data.by_competition.filter((c) => tier === 'all' || c.tier === tier),
    [data.by_competition, tier],
  )

  const bookWinsEverywhere = data.accuracy.every(
    (a) => a.brier_cecchino == null || a.brier_book == null || a.brier_cecchino > a.brier_book,
  )

  return (
    <Section
      title="Cecchino contro il mercato"
      note={`Tutte le partite eleggibili, quote di chiusura Bet365 · ${data.seasons.join(', ')} · ${data.lockbox_season} sotto chiave`}
    >
      <p className="mb-3 max-w-4xl text-xs leading-relaxed" style={{ color: 'var(--pi-muted)' }}>
        Qui non ci sono pattern: si misura il modello di base. Per ogni esito si confronta la
        probabilita&apos; data da Cecchino con quella &quot;pulita&quot; del bookmaker (quota di chiusura
        senza margine). Vince chi sbaglia meno sull&apos;esito reale.
      </p>

      <div className="mb-3 flex flex-wrap items-center gap-4">
        <Toggle options={data.tiers} value={tier} onChange={setTier} />
        <Toggle
          options={data.seasons.map((s) => ({ key: s, label: s }))}
          value={season}
          onChange={setSeason}
        />
      </div>

      {bookWinsEverywhere && (
        <div
          className="mb-3 rounded-xl border px-3 py-2 text-[11px] leading-relaxed"
          style={{ borderColor: 'rgba(217,90,87,0.45)', background: 'rgba(217,90,87,0.07)', color: '#f1b3b1' }}
        >
          <strong>Lettura:</strong> in ogni famiglia di mercato, in ogni stagione e in entrambe le fasce di
          campionati la quota di chiusura prevede meglio di Cecchino. Nessuna combinazione fa eccezione.
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="pi-tile">
          <div className="mb-1 text-xs font-semibold">Quanto sbaglia Cecchino in piu&apos; del bookmaker · {season}</div>
          <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Errore medio (Brier) di Cecchino rispetto a quello della quota di chiusura. A destra dello zero
            Cecchino sbaglia di piu&apos;, a sinistra sbaglierebbe di meno.
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={seasonGap} layout="vertical" margin={{ left: 4, right: 36 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
              <XAxis type="number" unit="%" tick={AXIS} stroke={GRID} domain={[(min: number) => Math.min(0, min), 'auto']} />
              <YAxis type="category" dataKey="family" width={120} tick={AXIS} stroke={GRID} />
              <ReferenceLine x={0} stroke="#e8eef9" strokeDasharray="4 3" />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                cursor={{ fill: 'rgba(217,90,87,0.06)' }}
                formatter={(v) => [`${signedPct(Number(v))} di errore`, 'Cecchino vs bookmaker']}
              />
              <Bar dataKey="gap" maxBarSize={20} radius={[0, 4, 4, 0]}>
                {seasonGap.map((d) => (
                  <Cell key={d.family} fill={d.gap > 0 ? BELOW_CHANCE : ABOVE_CHANCE} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="pi-scroll mt-2">
            <table className="pi-table">
              <thead>
                <tr>
                  <th>Famiglia</th>
                  {data.seasons.map((s) => (
                    <th key={s}>{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {accuracyRows.map((r) => (
                  <tr key={String(r.family)}>
                    <td className="font-semibold">{r.family}</td>
                    {data.seasons.map((s) => (
                      <td key={s} className="tabular-nums" title={`Brier Cecchino ${r[`${s}__c`]} · Bet365 ${r[`${s}__b`]}`}>
                        <span style={{ color: Number(r[s] ?? 0) > 0 ? BELOW_CHANCE : ABOVE_CHANCE }}>
                          {signedPct(r[s] as number | null)}
                        </span>
                        <span className="ml-1 text-[10px]" style={{ color: 'var(--pi-muted)' }}>
                          {Number(r[`${s}__c`] ?? 0).toFixed(3)} / {Number(r[`${s}__b`] ?? 0).toFixed(3)}
                        </span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="pi-tile">
          <div className="mb-1 text-xs font-semibold">Quando Cecchino vede piu&apos; del bookmaker, ha ragione? · {season}</div>
          <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Tutte le giocate raggruppate per quanto la probabilita&apos; di Cecchino supera quella del
            bookmaker. Se Cecchino avesse ragione, a destra la linea delle vinte salirebbe verso la sua.
            Se resta sulla linea del bookmaker, il &quot;valore&quot; visto era un errore di stima.
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={curve} margin={{ left: -8, right: 12, top: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <XAxis dataKey="label" tick={{ ...AXIS, fontSize: 10 }} stroke={GRID} interval={0} />
              <YAxis unit="%" tick={AXIS} stroke={GRID} domain={[0, 80]} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                cursor={{ stroke: '#8494b0', strokeDasharray: '3 3' }}
                formatter={(v, name) => [
                  `${Number(v).toFixed(1)}%`,
                  name === 'won_pct' ? 'Vinte davvero' : name === 'fair_pct' ? 'Probabilita\' bookmaker' : 'Probabilita\' Cecchino',
                ]}
                labelFormatter={(l) => `Cecchino rispetto al bookmaker: ${l}`}
              />
              <Legend
                formatter={(v) => (v === 'won_pct' ? 'Vinte davvero' : v === 'fair_pct' ? 'Bookmaker' : 'Cecchino')}
                wrapperStyle={{ fontSize: 11, color: '#8494b0' }}
              />
              <Line dataKey="cecchino_pct" stroke={SEASON_DISCOVERY} strokeWidth={2} dot={{ r: 4, fill: SEASON_DISCOVERY }} />
              <Line dataKey="fair_pct" stroke={BOOK_LINE} strokeWidth={2} strokeDasharray="5 4" dot={{ r: 4, fill: BOOK_LINE }} />
              <Line dataKey="won_pct" stroke={SEASON_VALIDATION} strokeWidth={2} dot={{ r: 4, fill: SEASON_VALIDATION }} />
            </LineChart>
          </ResponsiveContainer>
          <div className="pi-scroll mt-2">
            <table className="pi-table">
              <thead>
                <tr>
                  <th>Cecchino vs book</th>
                  <th>Giocate</th>
                  <th>Vinte</th>
                  <th>Book</th>
                  <th>Cecchino</th>
                  <th>Quota media</th>
                  <th>ROI</th>
                </tr>
              </thead>
              <tbody>
                {curve.map((v) => (
                  <tr key={v.bucket}>
                    <td className="font-semibold">{v.label}</td>
                    <td className="tabular-nums">{v.n.toLocaleString('it-IT')}</td>
                    <td className="tabular-nums">{v.won_pct?.toFixed(1)}%</td>
                    <td className="tabular-nums" style={{ color: 'var(--pi-muted)' }}>{v.fair_pct?.toFixed(1)}%</td>
                    <td className="tabular-nums" style={{ color: 'var(--pi-muted)' }}>{v.cecchino_pct?.toFixed(1)}%</td>
                    <td className="tabular-nums">{v.avg_quota?.toFixed(2)}</td>
                    <td className="tabular-nums font-semibold" style={{ color: (v.roi_pct ?? 0) >= 0 ? ABOVE_CHANCE : BELOW_CHANCE }}>
                      {signedPct(v.roi_pct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="pi-tile mt-3">
        <div className="mb-1 text-xs font-semibold">Campionato per campionato · 1X2 finale, tutte le stagioni</div>
        <div className="mb-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          Ordinati da dove Cecchino si avvicina di piu&apos; al bookmaker. Il margine e&apos; quanto trattiene
          Bet365 sull&apos;1X2 di chiusura; il ROI e&apos; quello che si otterrebbe giocando ogni esito.
        </div>
        <div className="pi-scroll" style={{ maxHeight: 420 }}>
          <table className="pi-table">
            <thead>
              <tr>
                <th>Campionato</th>
                <th>Fascia</th>
                <th>Esiti</th>
                <th>Errore Cecchino</th>
                <th>Errore book</th>
                <th>Cecchino vs book</th>
                <th>Margine book</th>
                <th>ROI giocando tutto</th>
              </tr>
            </thead>
            <tbody>
              {competitions.map((c) => {
                const g = gapPct(c.brier_cecchino, c.brier_book)
                return (
                  <tr key={c.competition}>
                    <td className="font-semibold">{c.competition}</td>
                    <td style={{ color: 'var(--pi-muted)' }}>{c.tier === 'top' ? 'Prima divisione' : 'Inferiore'}</td>
                    <td className="tabular-nums">{c.n.toLocaleString('it-IT')}</td>
                    <td className="tabular-nums">{c.brier_cecchino?.toFixed(4)}</td>
                    <td className="tabular-nums">{c.brier_book?.toFixed(4)}</td>
                    <td className="tabular-nums font-semibold" style={{ color: (g ?? 0) > 0 ? BELOW_CHANCE : ABOVE_CHANCE }}>
                      {signedPct(g)}
                    </td>
                    <td className="tabular-nums">{c.margin_pct?.toFixed(1)}%</td>
                    <td className="tabular-nums" style={{ color: (c.roi_all_bets_pct ?? 0) >= 0 ? ABOVE_CHANCE : BELOW_CHANCE }}>
                      {signedPct(c.roi_all_bets_pct)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  )
}
