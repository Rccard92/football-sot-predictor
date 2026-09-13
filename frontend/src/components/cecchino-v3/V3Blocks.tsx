import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Section } from '../pattern-insights/PatternInsightsShell'
import { FAMILY_LABELS, type V3Evaluation, type V3Family, type V3Metric, type V3Run } from '../../lib/cecchinoV3Api'

// Stessa coppia validata di Pattern Insights (fondo #0e1526): V3 verde acqua,
// V2 viola, bookmaker grigio neutro tratteggiato.
const COLOR_V3 = '#1ea68f'
const COLOR_V2 = '#8a78e6'
const COLOR_BOOK = '#8494b0'
const COLOR_BAD = '#d95a57'
const AXIS = { fill: '#8494b0', fontSize: 11 }
const GRID = '#1e2a44'
const TOOLTIP_STYLE = {
  background: '#131c31',
  border: '1px solid #1e2a44',
  borderRadius: 10,
  color: '#e8eef9',
  fontSize: 12,
}

const FAMILIES: V3Family[] = ['FT_1X2', 'DOUBLE_CHANCE', 'FT_OVER_UNDER', 'HT_1X2']

function signed(v: number | null | undefined, d = 1): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(d)}%`
}

function brier(v: number | null | undefined): string {
  return v == null ? '—' : v.toFixed(4)
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

function PassChip({ passed }: { passed: boolean }) {
  const color = passed ? COLOR_V3 : COLOR_BAD
  return (
    <span
      className="whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold"
      style={{ border: `1px solid ${color}`, color: 'var(--pi-text)' }}
    >
      <span style={{ color }}>{passed ? '✓' : '✗'}</span> {passed ? 'Superato' : 'Non superato'}
    </span>
  )
}

export function ExamBlock({ evaluation }: { evaluation: V3Evaluation }) {
  const exam = evaluation.exam
  const color = exam.passed ? COLOR_V3 : COLOR_BAD
  return (
    <Section title="Esame della Fase 1" note="Criteri fissati prima di vedere i risultati">
      <div
        className="mb-4 rounded-xl border px-4 py-3"
        style={{ borderColor: `${color}88`, background: `${color}14` }}
      >
        <div className="text-2xl font-bold" style={{ color }}>
          {exam.passed ? 'Esame superato' : 'Esame non superato'}
        </div>
        <ul className="mt-1 list-disc pl-5 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          {exam.rules.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </div>

      <div className="pi-scroll">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Mercato</th>
              {evaluation.judge_seasons.map((s) => (
                <th key={s}>{s} · errore V3 / V2</th>
              ))}
              <th>Esito</th>
            </tr>
          </thead>
          <tbody>
            {exam.accuracy_vs_v2.map((f) => (
              <tr key={f.family}>
                <td className="font-semibold">{FAMILY_LABELS[f.family]}</td>
                {f.seasons.map((s) => (
                  <td key={s.season_label} className="tabular-nums">
                    <span style={{ color: s.passed ? COLOR_V3 : COLOR_BAD }} className="font-semibold">
                      {brier(s.brier_v3)}
                    </span>
                    <span style={{ color: 'var(--pi-muted)' }}> / {brier(s.brier_v2)}</span>
                  </td>
                ))}
                <td>
                  <PassChip passed={f.passed} />
                </td>
              </tr>
            ))}
            {exam.calibration.map((c) => (
              <tr key={`cal-${c.family}`}>
                <td className="font-semibold">Calibrazione · {FAMILY_LABELS[c.family]}</td>
                <td colSpan={evaluation.judge_seasons.length} className="tabular-nums">
                  errore medio {c.calibration_error_pct?.toFixed(2) ?? '—'} punti (massimo {c.max_allowed_pct})
                </td>
                <td>
                  <PassChip passed={c.passed} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

type Scope = 'all' | 'top' | 'lower' | 'mid' | 'final'

export function AccuracyBlock({ evaluation }: { evaluation: V3Evaluation }) {
  const [scope, setScope] = useState<Scope>('all')
  const seasons = useMemo(
    () => Array.from(new Set(evaluation.by_season.map((r) => r.season_label))).sort(),
    [evaluation.by_season],
  )

  const pick = (family: V3Family, season: string): V3Metric | undefined => {
    if (scope === 'all') return evaluation.by_season.find((r) => r.family === family && r.season_label === season)
    if (scope === 'top' || scope === 'lower')
      return evaluation.by_tier.find((r) => r.family === family && r.season_label === season && r.tier === scope)
    return evaluation.by_phase.find((r) => r.family === family && r.season_label === season && r.phase === scope)
  }

  return (
    <Section
      title="Precisione a confronto"
      note="Errore medio (Brier): piu' basso e' meglio. Stesse partite per V3, V2 e bookmaker."
    >
      <p className="mb-3 max-w-4xl text-xs leading-relaxed" style={{ color: 'var(--pi-muted)' }}>
        Ogni cella mostra l&apos;errore della V3, della V2 e della quota di chiusura. Le percentuali dicono di quanto
        la V3 sbaglia meno (negativo) o di piu&apos; (positivo) rispetto alla V2 e al bookmaker. Il{' '}
        {evaluation.warmup_season} e&apos; la stagione di rodaggio: si mostra per completezza ma non conta
        nell&apos;esame.
      </p>
      <div className="mb-3">
        <Toggle<Scope>
          options={[
            { key: 'all', label: 'Tutte le partite' },
            { key: 'top', label: 'Prime divisioni' },
            { key: 'lower', label: 'Divisioni inferiori' },
            { key: 'mid', label: 'Fase centrale' },
            { key: 'final', label: 'Ultime 5 giornate' },
          ]}
          value={scope}
          onChange={setScope}
        />
      </div>
      <div className="pi-scroll">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Mercato</th>
              {seasons.map((s) => (
                <th key={s}>
                  {s}
                  {s === evaluation.warmup_season ? ' (rodaggio)' : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {FAMILIES.map((family) => (
              <tr key={family}>
                <td className="font-semibold">{FAMILY_LABELS[family]}</td>
                {seasons.map((s) => {
                  const r = pick(family, s)
                  return (
                    <td key={s} className="tabular-nums" style={{ opacity: s === evaluation.warmup_season ? 0.55 : 1 }}>
                      {r ? (
                        <>
                          <div>
                            <span style={{ color: COLOR_V3 }} className="font-semibold">
                              {brier(r.brier_v3)}
                            </span>
                            <span style={{ color: COLOR_V2 }}> · {brier(r.brier_v2)}</span>
                            <span style={{ color: COLOR_BOOK }}> · {brier(r.brier_book)}</span>
                          </div>
                          <div className="text-[10px]" style={{ color: 'var(--pi-muted)' }}>
                            vs V2{' '}
                            <span style={{ color: (r.v3_vs_v2_pct ?? 0) <= 0 ? COLOR_V3 : COLOR_BAD }}>
                              {signed(r.v3_vs_v2_pct)}
                            </span>{' '}
                            · vs book{' '}
                            <span style={{ color: (r.v3_vs_book_pct ?? 0) <= 0 ? COLOR_V3 : COLOR_BAD }}>
                              {signed(r.v3_vs_book_pct)}
                            </span>{' '}
                            · {r.n.toLocaleString('it-IT')} esiti
                          </div>
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
        <span>
          <span style={{ color: COLOR_V3 }}>■</span> V3
        </span>
        <span>
          <span style={{ color: COLOR_V2 }}>■</span> V2
        </span>
        <span>
          <span style={{ color: COLOR_BOOK }}>■</span> Quota di chiusura
        </span>
      </div>
    </Section>
  )
}

export function CalibrationBlock({ evaluation }: { evaluation: V3Evaluation }) {
  const families = Array.from(new Set(evaluation.calibration.map((c) => c.family)))
  return (
    <Section
      title="Calibrazione"
      note={`Quando la V3 dice X%, succede davvero X%? Stagioni ${evaluation.judge_seasons.join(', ')}`}
    >
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {families.map((family) => {
          const data = evaluation.calibration
            .filter((c) => c.family === family)
            .map((c) => ({
              p: Math.round((c.avg_probability_v3 ?? 0) * 1000) / 10,
              won: Math.round((c.won_rate ?? 0) * 1000) / 10,
              n: c.n,
            }))
          return (
            <div key={family} className="pi-tile">
              <div className="mb-1 text-xs font-semibold">
                {FAMILY_LABELS[family]} · errore medio{' '}
                {evaluation.calibration_error[family]?.v3_pct?.toFixed(2) ?? '—'} punti
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={data} margin={{ left: -8, right: 12, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                  <XAxis dataKey="p" type="number" domain={[0, 100]} unit="%" tick={AXIS} stroke={GRID} />
                  <YAxis domain={[0, 100]} unit="%" tick={AXIS} stroke={GRID} />
                  <ReferenceLine
                    segment={[
                      { x: 0, y: 0 },
                      { x: 100, y: 100 },
                    ]}
                    stroke={COLOR_BOOK}
                    strokeDasharray="5 4"
                  />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    formatter={(v, name) => [`${Number(v).toFixed(1)}%`, name === 'won' ? 'Successo reale' : name]}
                    labelFormatter={(l) => `Probabilita' V3 media ${l}%`}
                  />
                  <Legend
                    formatter={(v) => (v === 'won' ? 'Successo reale (la diagonale e\' la perfezione)' : v)}
                    wrapperStyle={{ fontSize: 11, color: '#8494b0' }}
                  />
                  <Line dataKey="won" stroke={COLOR_V3} strokeWidth={2} dot={{ r: 4, fill: COLOR_V3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )
        })}
      </div>
    </Section>
  )
}

export function CompetitionBlock({ evaluation }: { evaluation: V3Evaluation }) {
  const rows = [...evaluation.by_competition].sort((a, b) => (a.v3_vs_book_pct ?? 0) - (b.v3_vs_book_pct ?? 0))
  return (
    <Section
      title="Campionato per campionato"
      note={`1X2 finale · stagioni di giudizio insieme · ordinati da dove la V3 e' piu' vicina al bookmaker`}
    >
      <div className="pi-scroll" style={{ maxHeight: 460 }}>
        <table className="pi-table">
          <thead>
            <tr>
              <th>Campionato</th>
              <th>Fascia</th>
              <th>Esiti</th>
              <th>Errore V3</th>
              <th>Errore V2</th>
              <th>Errore book</th>
              <th>V3 vs V2</th>
              <th>V3 vs book</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.competition_name}>
                <td className="font-semibold">{r.competition_name}</td>
                <td style={{ color: 'var(--pi-muted)' }}>{r.tier === 'top' ? 'Prima divisione' : 'Inferiore'}</td>
                <td className="tabular-nums">{r.n.toLocaleString('it-IT')}</td>
                <td className="tabular-nums font-semibold" style={{ color: COLOR_V3 }}>
                  {brier(r.brier_v3)}
                </td>
                <td className="tabular-nums">{brier(r.brier_v2)}</td>
                <td className="tabular-nums">{brier(r.brier_book)}</td>
                <td className="tabular-nums" style={{ color: (r.v3_vs_v2_pct ?? 0) <= 0 ? COLOR_V3 : COLOR_BAD }}>
                  {signed(r.v3_vs_v2_pct)}
                </td>
                <td className="tabular-nums" style={{ color: (r.v3_vs_book_pct ?? 0) <= 0 ? COLOR_V3 : COLOR_BAD }}>
                  {signed(r.v3_vs_book_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

export function RunDetailsBlock({ run }: { run: V3Run }) {
  const summary = run.summary
  if (!summary) return null
  const seasons = Object.keys(summary.seasons).sort()
  const coverage = summary.evaluation.coverage
  return (
    <Section title="Dettagli del calcolo" note={`Calcolo #${run.id} · ${summary.elapsed_seconds.toFixed(0)} secondi`}>
      <div className="pi-scroll">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Stagione</th>
              <th>Partite</th>
              <th>Idonee (≥5 giocate)</th>
              <th>Inizio</th>
              <th>Centrale</th>
              <th>Ultime 5</th>
              <th>Confrontabili con V2</th>
              <th>Parametri usati</th>
            </tr>
          </thead>
          <tbody>
            {seasons.map((s) => {
              const c = summary.seasons[s]
              const cov = coverage.find((x) => x.season_label === s)
              const h = summary.chosen_hyper[s]
              return (
                <tr key={s}>
                  <td className="font-semibold">{s}</td>
                  <td className="tabular-nums">{c.matches.toLocaleString('it-IT')}</td>
                  <td className="tabular-nums">{c.eligible.toLocaleString('it-IT')}</td>
                  <td className="tabular-nums">{c.early.toLocaleString('it-IT')}</td>
                  <td className="tabular-nums">{c.mid.toLocaleString('it-IT')}</td>
                  <td className="tabular-nums">{c.final.toLocaleString('it-IT')}</td>
                  <td className="tabular-nums">{cov ? cov.common_matches.toLocaleString('it-IT') : '—'}</td>
                  <td className="tabular-nums text-[11px]" style={{ color: 'var(--pi-muted)' }}>
                    {h ? `invecchiamento ${h.xi} · scarto squadre ${h.sigma}` : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
        I parametri di ogni stagione sono quelli che hanno previsto meglio la stagione precedente; nel rodaggio si usa
        il valore di partenza. Nessuna stagione di giudizio e&apos; usata per sceglierli.
      </p>
    </Section>
  )
}
