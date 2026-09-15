import { useEffect, useMemo, useState } from 'react'
import {
  getLiveFixture,
  type LiveBalancePillar,
  type LiveFixtureResponse,
  type LiveGoalPillar,
  type LiveModelPrediction,
} from '../../lib/cecchinoLiveApi'
import { MARKET_LABELS } from '../../lib/masterPatternApi'
import { formatFetchError } from '../../utils/formatFetchError'
import {
  edgeClassName,
  isKpiPrimaryRow,
  purchasabilityV31BadgeClass,
  vantaggioClassName,
} from './cecchinoKpiUiUtils'
import { CecchinoPatternHero } from './CecchinoPatternHero'
import { CecchinoPurchasabilityIndexV25 } from './CecchinoPurchasabilityIndexV25'
import { groupPatternSignals } from './cecchinoPatternUtils'
import {
  todayBadgeActive,
  todayBadgeMuted,
  todayBadgeOk,
  todayCard,
  todayCardPadding,
  todaySectionSubtitle,
  todaySectionTitle,
} from './cecchinoTodayStyles'

/** Scheda V2.5 in Cecchino Today: stessi blocchi e stessa grafica della V2, dati del registro live. */

const MARKET_ORDER = [
  'HOME', 'DRAW', 'AWAY', 'ONE_X', 'X_TWO', 'ONE_TWO', 'HOME_PT', 'DRAW_PT', 'AWAY_PT',
  'OVER_0_5', 'UNDER_0_5', 'OVER_1_5', 'UNDER_1_5', 'OVER_2_5', 'UNDER_2_5', 'OVER_3_5', 'UNDER_3_5',
]

const SEGNO: Record<string, string> = {
  HOME: '1', DRAW: 'X', AWAY: '2', ONE_X: '1X', X_TWO: 'X2', ONE_TWO: '12',
  HOME_PT: '1 PT', DRAW_PT: 'X PT', AWAY_PT: '2 PT',
  OVER_0_5: 'Over 0.5', UNDER_0_5: 'Under 0.5', OVER_1_5: 'Over 1.5', UNDER_1_5: 'Under 1.5',
  OVER_2_5: 'Over 2.5', UNDER_2_5: 'Under 2.5', OVER_3_5: 'Over 3.5', UNDER_3_5: 'Under 3.5',
}

const CLASS_LABELS: Record<string, string> = {
  very_low: 'Molto bassa', low: 'Bassa', medium: 'Media', high: 'Alta', very_high: 'Molto alta',
  strong_balance: 'Equilibrio forte', balance: 'Equilibrio', transition: 'Transizione', imbalance: 'Squilibrio',
  very_weak: 'Molto debole', weak: 'Debole', moderate: 'Moderata', strong: 'Forte', very_strong: 'Molto forte',
  not_confirmed: 'Non confermata', partial: 'Parziale', confirmed: 'Confermata', strongly_confirmed: 'Fortemente confermata',
}

type PillarInfo = { key: string; title: string; question: string; indexLabel: string }

const BALANCE_INFO: PillarInfo[] = [
  { key: 'f36', title: 'Geometria della partita', question: 'Quanto sono lontane le probabilità di 1 e di 2?', indexLabel: 'Indice equilibrio' },
  { key: 'dominance', title: 'Convinzione del modello', question: "Quanto il Cecchino è deciso sull'esito più probabile?", indexLabel: 'Indice convinzione' },
  { key: 'draw_credibility', title: 'Credibilità della X', question: 'Quanto è credibile il pareggio rispetto alle partite dello storico?', indexLabel: 'Indice X' },
  { key: 'gap_coherence', title: 'Coerenza picchetti / modello gol', question: 'I picchetti e il modello gol indicano lo stesso lato con la stessa forza?', indexLabel: 'Indice coerenza' },
]

const GOAL_INFO: { key: string; title: string; hint: string }[] = [
  { key: 'offensive_production', title: 'Produzione offensiva', hint: 'Gol fatti dalle due squadre rispetto alla media del campionato' },
  { key: 'defensive_solidity', title: 'Solidità difensiva', hint: 'Gol subiti: alta = le difese concedono poco' },
  { key: 'match_tempo', title: 'Ritmo partita', hint: 'Gol attesi della partita rispetto al campionato' },
  { key: 'offensive_stability', title: 'Stabilità offensiva', hint: 'Costanza nel segnare nelle ultime 10 partite' },
]

function pct(v: number | null | undefined, d = 1): string {
  return v == null ? '—' : `${(v * 100).toLocaleString('it-IT', { maximumFractionDigits: d, minimumFractionDigits: d })}%`
}

function num(v: number | null | undefined, d = 2): string {
  return v == null ? '—' : v.toLocaleString('it-IT', { maximumFractionDigits: d, minimumFractionDigits: d })
}

function signed(v: number | null | undefined, d = 1, suffix = '%'): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toLocaleString('it-IT', { maximumFractionDigits: d, minimumFractionDigits: d })}${suffix}`
}

function cls(v: string | null | undefined): string {
  return v ? (CLASS_LABELS[v] ?? v) : '—'
}

// una sola lettura per partita anche se più blocchi della scheda la usano
const LIVE_CACHE_MS = 120_000
const liveCache = new Map<number, { at: number; promise: Promise<LiveFixtureResponse> }>()

function fetchLiveFixture(id: number): Promise<LiveFixtureResponse> {
  const hit = liveCache.get(id)
  if (hit && Date.now() - hit.at < LIVE_CACHE_MS) return hit.promise
  const promise = getLiveFixture(id)
  liveCache.set(id, { at: Date.now(), promise })
  promise.catch(() => liveCache.delete(id))
  return promise
}

export function useLiveFixture(todayFixtureId: number | undefined) {
  const [data, setData] = useState<LiveFixtureResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    if (todayFixtureId == null) return
    let alive = true
    setLoading(true)
    setError(null)
    fetchLiveFixture(todayFixtureId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(formatFetchError(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [todayFixtureId])
  return { data, error, loading }
}

export function SourceBadge({ p }: { p: LiveModelPrediction }) {
  if (p.source === 'registro') {
    const frozen = p.frozen_at ? new Date(p.frozen_at).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' }) : '—'
    return (
      <span className={p.status === 'settled' ? todayBadgeOk : todayBadgeActive}>
        {p.status === 'settled' ? 'Registrata · esito' : 'Registrata'} · {frozen}
      </span>
    )
  }
  return <span className={todayBadgeMuted}>Anteprima non registrata</span>
}

export function Badge({ children, tone = 'slate' }: { children: React.ReactNode; tone?: 'slate' | 'amber' | 'emerald' | 'sky' | 'dark' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700',
    amber: 'bg-amber-50 text-amber-900 ring-1 ring-amber-200',
    emerald: 'bg-emerald-50 text-emerald-800',
    sky: 'bg-sky-50 text-sky-800',
    dark: 'bg-slate-900 text-white',
  }
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${tones[tone]}`}>{children}</span>
}

// ---------------------------------------------------------------------------
// Acquistabilità
// ---------------------------------------------------------------------------

export function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className="text-sm font-semibold tabular-nums text-slate-900">{value}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pannello KPI (stessa grafica della V2)
// ---------------------------------------------------------------------------

function ResultCell({ won }: { won: boolean | null | undefined }) {
  if (won == null) return <span className="text-slate-500">—</span>
  return won ? (
    <span className="rounded-full bg-emerald-600 px-2 py-0.5 text-[10px] font-semibold text-white">Vinta</span>
  ) : (
    <span className="rounded-full bg-slate-600 px-2 py-0.5 text-[10px] font-semibold text-slate-100">Persa</span>
  )
}

export function KpiPanel({
  p,
  title = 'PANNELLO KPI V2.5',
  showPurchasability = true,
}: {
  p: LiveModelPrediction
  title?: string
  showPurchasability?: boolean
}) {
  const markets = p.markets ?? {}
  const results = p.result?.markets ?? {}
  const rows = MARKET_ORDER.filter((k) => markets[k])
  const th = 'border-r border-slate-500/40 px-1.5 py-2 text-[10px] font-semibold uppercase text-slate-200'
  const td = 'border-r border-slate-500/40 px-1.5 py-2.5 whitespace-nowrap tabular-nums'
  return (
    <section className="overflow-hidden rounded-xl border border-slate-300 shadow-md">
      <div className="bg-[#1e3a5f] px-4 py-3">
        <h3 className="text-center text-sm font-bold tracking-wide text-white sm:text-left sm:text-base">{title}</h3>
        <p className="mt-1 text-center text-[10px] text-slate-300 sm:text-left sm:text-xs">
          Book · Bet365 · probabilità Bet365 senza margine · valore atteso = guadagno medio per 1 € giocato alla quota Bet365
        </p>
      </div>

      <div className="hidden overflow-x-auto bg-[#163352] xl:block">
        <table className="w-full table-fixed border-collapse text-center text-[11px] text-white 2xl:text-xs">
          <thead>
            <tr className="border-b border-slate-400/50 bg-[#0f2847]">
              <th className={`${th} w-[10%] text-left text-slate-300`}>Segno</th>
              <th className={`${th} w-[9%]`}>Quota Book</th>
              <th className={`${th} w-[9%] text-amber-200`}>Quota Cecchino</th>
              <th className={`${th} w-[10%]`}>Prob. Book</th>
              <th className={`${th} w-[10%]`}>Prob. Cecchino</th>
              <th className={`${th} w-[10%]`}>Vant. Prob.</th>
              <th className={`${th} w-[10%]`}>Valore atteso</th>
              <th className={`${th} w-[8%]`}>Rating</th>
              {showPurchasability && <th className={`${th} w-[14%]`}>Acquistabilità</th>}
              <th className="w-[10%] px-1.5 py-2 text-[10px] font-semibold uppercase text-slate-200">Esito</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((k) => {
              const m = markets[k]
              const segno = SEGNO[k] ?? k
              const primary = isKpiPrimaryRow(segno)
              return (
                <tr key={k} className={`border-b border-slate-600/40 hover:bg-slate-800/25 ${primary ? 'bg-[#1a3d5c]/60' : ''}`}>
                  <td className={`${td} text-left ${primary ? 'font-bold text-white' : 'font-medium text-slate-300'}`}>
                    {segno}
                    {m.signal_active && <span className="ml-1.5 rounded bg-sky-500/80 px-1 py-px text-[9px] font-semibold uppercase">segnale</span>}
                  </td>
                  <td className={`${td} text-slate-100`}>{num(m.quota_book)}</td>
                  <td className={`${td} font-semibold text-amber-100`}>{num(m.quota_cecchino)}</td>
                  <td className={`${td} text-slate-100`}>{pct(m.prob_book_fair, 2)}</td>
                  <td className={`${td} text-slate-100`}>{pct(m.probability, 2)}</td>
                  <td className={`${td} ${vantaggioClassName(m.vantaggio_prob)}`}>
                    {m.vantaggio_prob == null ? '—' : signed(m.vantaggio_prob * 100, 2, ' pp')}
                  </td>
                  <td className={`${td} ${edgeClassName(m.edge_pct)}`}>{signed(m.edge_pct, 2)}</td>
                  <td className="border-r border-slate-500/40 px-1.5 py-2.5">
                    {m.rating != null ? (
                      <span className="inline-flex rounded-full bg-slate-600 px-2 py-0.5 text-[10px] font-semibold tabular-nums text-slate-100">{m.rating}</span>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                  {showPurchasability && (
                    <td className="border-r border-slate-500/40 px-1.5 py-2.5">
                      {m.buyability_score != null ? (
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${purchasabilityV31BadgeClass(m.buyability_class)}`}>
                          <span className="tabular-nums">{m.buyability_score}</span>
                          <span>{m.buyability_class}</span>
                        </span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                  )}
                  <td className="px-1.5 py-2.5">
                    <ResultCell won={results[k]?.won} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 bg-[#163352] p-3 xl:hidden">
        {rows.map((k) => {
          const m = markets[k]
          return (
            <article key={k} className="rounded-lg border border-slate-500/40 bg-[#1a3d5c]/40 p-3 text-xs text-white">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="font-semibold">{SEGNO[k] ?? k}</span>
                {showPurchasability && m.buyability_score != null && (
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${purchasabilityV31BadgeClass(m.buyability_class)}`}>
                    {m.buyability_score} {m.buyability_class}
                  </span>
                )}
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 tabular-nums">
                <dt className="text-slate-400">Quota Book</dt>
                <dd>{num(m.quota_book)}</dd>
                <dt className="text-slate-400">Quota Cecchino</dt>
                <dd className="text-amber-100">{num(m.quota_cecchino)}</dd>
                <dt className="text-slate-400">Prob. Book</dt>
                <dd>{pct(m.prob_book_fair, 2)}</dd>
                <dt className="text-slate-400">Prob. Cecchino</dt>
                <dd>{pct(m.probability, 2)}</dd>
                <dt className="text-slate-400">Vant. Prob.</dt>
                <dd className={vantaggioClassName(m.vantaggio_prob)}>{m.vantaggio_prob == null ? '—' : signed(m.vantaggio_prob * 100, 2, ' pp')}</dd>
                <dt className="text-slate-400">Valore atteso</dt>
                <dd className={edgeClassName(m.edge_pct)}>{signed(m.edge_pct, 2)}</dd>
                <dt className="text-slate-400">Esito</dt>
                <dd>
                  <ResultCell won={results[k]?.won} />
                </dd>
              </dl>
            </article>
          )
        })}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Equilibrio vs Squilibrio
// ---------------------------------------------------------------------------

function balanceReading(key: string, pillar: LiveBalancePillar | undefined, classKey: string | null | undefined): string {
  const c = classKey ?? pillar?.class_key
  const dir = pillar?.direction
  switch (key) {
    case 'f36':
      if (c === 'strong_balance') return 'Probabilità di 1 e 2 molto vicine: partita aperta, nessun lato favorito.'
      if (c === 'balance') return 'Leggera differenza tra le due squadre, la partita resta equilibrata.'
      if (c === 'transition') return `Una squadra è avanti${dir ? ` (lato ${dir})` : ''}, ma senza un dominio netto.`
      if (c === 'imbalance') return `Squilibrio netto a favore del lato ${dir ?? '—'}.`
      return 'Lettura non disponibile.'
    case 'dominance':
      return c ? `Esito più probabile per il Cecchino: ${dir ?? '—'}. Convinzione ${cls(c).toLowerCase()} rispetto alle partite dello storico.` : 'Lettura non disponibile.'
    case 'draw_credibility':
      return c
        ? `Pareggio al ${pct(pillar?.raw_value)} per il Cecchino: credibilità ${cls(c).toLowerCase()} rispetto alle partite dello storico.`
        : 'Lettura non disponibile.'
    case 'gap_coherence':
      if (c === 'strongly_confirmed' || c === 'confirmed') return 'Picchetti e modello gol vedono la partita allo stesso modo: lettura confermata.'
      if (c === 'partial') return 'Picchetti e modello gol concordano solo in parte: lettura da prendere con cautela.'
      if (c === 'weak' || c === 'not_confirmed') return 'Picchetti e modello gol vedono la partita in modo diverso: lettura poco affidabile.'
      return 'Lettura non disponibile (manca il modello gol).'
    default:
      return ''
  }
}

function BalancePanel({ p }: { p: LiveModelPrediction }) {
  const detail = p.modules?.balance_pillars ?? {}
  const classes = p.modules?.balance_classes ?? {}
  return (
    <section className="space-y-4">
      <div>
        <h3 className={todaySectionTitle}>Equilibrio vs Squilibrio V2.5</h3>
        <p className={`mt-1 ${todaySectionSubtitle}`}>Quattro letture distinte della struttura della partita.</p>
        <p className="mt-1 text-xs text-slate-500">
          Indici 0–100 calcolati solo sul Cecchino (senza quote book) e confrontati con le partite dello storico. Non vanno confrontati tra loro.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {BALANCE_INFO.map((info, i) => {
          const pillar = detail[info.key]
          const classKey = classes[info.key] ?? pillar?.class_key
          return (
            <article key={info.key} className={`${todayCard} ${todayCardPadding} flex flex-col gap-3`}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Pilastro {i + 1}</p>
                  <h4 className="text-sm font-semibold text-slate-900">{info.title}</h4>
                </div>
                <span className="inline-flex shrink-0 items-center rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white ring-1 ring-slate-800">
                  V2.5
                </span>
              </div>
              <p className="text-xs text-slate-500">{info.question}</p>
              <div className="flex items-end justify-between gap-3 border-t border-slate-100 pt-3">
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-slate-400">{info.indexLabel}</p>
                  <p className="text-2xl font-semibold tabular-nums text-slate-900">{num(pillar?.index, 1)}</p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] uppercase tracking-wide text-slate-400">Classe</p>
                  <p className="text-sm font-medium text-slate-800">{cls(classKey)}</p>
                  {pillar?.direction && info.key !== 'draw_credibility' && info.key !== 'gap_coherence' ? (
                    <p className="mt-0.5 text-xs text-slate-500">
                      {info.key === 'f36' ? `Inclinazione: lato ${pillar.direction}` : `Scenario dominante: ${pillar.direction}`}
                    </p>
                  ) : null}
                </div>
              </div>
              <p className="text-xs leading-relaxed text-slate-700">{balanceReading(info.key, pillar, classKey)}</p>
            </article>
          )
        })}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Intensità Goal
// ---------------------------------------------------------------------------

function ProbBlock({ title, overLabel, underLabel, over, under }: { title: string; overLabel: string; underLabel: string; over: number | null | undefined; under: number | null | undefined }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2.5">
      <p className="text-xs font-semibold text-slate-800">{title}</p>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
        <div>
          <p className="text-[11px] text-slate-500">{overLabel}</p>
          <p className="font-semibold text-slate-900">{pct(over)}</p>
        </div>
        <div>
          <p className="text-[11px] text-slate-500">{underLabel}</p>
          <p className="font-semibold text-slate-900">{pct(under)}</p>
        </div>
      </div>
    </div>
  )
}

export function GoalIntensityPanel({
  p,
  model = 'V2.5',
  reference,
}: {
  p: LiveModelPrediction
  model?: string
  /** Storico con cui la partita viene confrontata, se diverso dal campionato. */
  reference?: string
}) {
  const markets = p.markets ?? {}
  const pillars = p.modules?.goal_intensity_pillars ?? {}
  const classes = p.modules?.goal_intensity_classes ?? {}
  const finalDetail = p.modules?.goal_intensity_final_detail
  const finalKey = finalDetail?.key ?? p.modules?.goal_intensity_final
  const xg = p.modules?.expected_goals
  const total = xg?.home != null && xg?.away != null ? xg.home + xg.away : null
  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <h3 className={todaySectionTitle}>Intensità Goal {model}</h3>
      <p className={todaySectionSubtitle}>
        Quanti gol ci si aspetta dalla partita, rispetto {reference ?? 'alla media del campionato'}. Non è un consiglio autonomo.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge tone="sky">Classe finale: {cls(finalKey)}</Badge>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
          <p className="text-[11px] text-slate-500">Indice intensità (0–100)</p>
          <p className="text-2xl font-semibold text-slate-900">{num(finalDetail?.score, 1)}</p>
          <p className="mt-1 text-[11px] text-slate-500">
            {reference ? 'Media dei quattro pilastri: posizione della partita tra quelle dello storico' : 'Posizione della probabilità Over 2.5 tra le partite dello storico'}
          </p>
        </div>
        {total != null && (
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
          <p className="text-[11px] text-slate-500">Stima totale gol</p>
          <p className="text-2xl font-semibold text-slate-900">{num(total, 2)}</p>
          <p className="mt-1 text-[11px] text-slate-500">
            {xg ? `Casa ${num(xg.home, 2)} · Ospite ${num(xg.away, 2)} (modello gol ${model})` : `Modello gol ${model}`}
          </p>
        </div>
        )}
        <ProbBlock title="Linea 1.5" overLabel="Over 1.5" underLabel="Under 1.5" over={markets.OVER_1_5?.probability} under={markets.UNDER_1_5?.probability} />
        <ProbBlock title="Linea 2.5" overLabel="Over 2.5" underLabel="Under 2.5" over={markets.OVER_2_5?.probability} under={markets.UNDER_2_5?.probability} />
      </div>

      <p className="mt-4 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Pilastri</p>
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {GOAL_INFO.map((info) => {
          const pl: LiveGoalPillar | undefined = pillars[info.key]
          return (
            <div key={info.key} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2">
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-800">{info.title}</p>
                <p className="text-[11px] text-slate-500">{reference ? info.hint.replace(/(alla media del campionato|al campionato)/, 'allo storico') : info.hint}</p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-sm font-semibold tabular-nums text-slate-900">{num(pl?.score, 0)}</p>
                <p className="text-[11px] text-slate-600">{cls(classes[info.key] ?? pl?.class_key)}</p>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Pattern Master
// ---------------------------------------------------------------------------

function meanOf(values: (number | null)[]): number | null {
  const v = values.filter((x): x is number => x != null)
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
}

const PATTERN_GROUPS_VISIBLE = 12
const PATTERNS_PER_GROUP_VISIBLE = 5

/** Pattern senza quota (tiri, corner, cartellini): in fondo alla scheda, solo osservazione. */
export function PatternPanel({
  p,
  title = 'Pattern Master V2.5 senza quota',
  model = 'V2.5',
}: {
  p: LiveModelPrediction
  title?: string
  model?: string
}) {
  const patterns = p.modules?.patterns
  const extra = patterns?.extra_stats
  const [openKey, setOpenKey] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const groups = useMemo(
    () => groupPatternSignals((patterns?.active ?? []).filter((x) => x.target_type !== 'market')),
    [patterns],
  )
  const results = p.result?.markets ?? {}
  const visible = showAll ? groups : groups.slice(0, PATTERN_GROUPS_VISIBLE)

  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className={todaySectionTitle}>{title}</h3>
          <p className={todaySectionSubtitle}>Tiri, corner e cartellini: Bet365 non ha quote nello storico, quindi restano solo in osservazione.</p>
        </div>
        <Badge tone="amber">In osservazione</Badge>
      </div>

      <details className="mt-3 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2 text-xs text-slate-600">
        <summary className="cursor-pointer font-semibold text-slate-700">Come si leggono</summary>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          <li>Un pattern è una combinazione di condizioni dei moduli (per esempio Equilibrio, Intensità Goal, differenze di tiri o corner delle squadre) che è stata vincente in tutte e 4 le stagioni.</li>
          <li>Qui compaiono solo i pattern senza quota le cui condizioni sono tutte vere in questa partita. I pattern con quota sono la predizione in cima alla scheda.</li>
          <li>Più pattern sulla stessa statistica e linea contano come un solo segnale: il numero indica quanti pattern diversi arrivano alla stessa conclusione.</li>
          <li>Percentuale di riuscita storica e scarto rispetto alla media del campionato. Senza quota non si può misurare il profitto: andamento reale in Osservazione live.</li>
        </ul>
      </details>

      {patterns?.status !== 'ok' ? (
        <p className="mt-3 text-sm text-slate-500">Pattern Master {model} non disponibili.</p>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <Stat label="Segnali senza quota" value={String(groups.length)} />
            <Stat label="Pattern accesi" value={`${patterns.active_count ?? 0} su ${patterns.patterns_total ?? 0}`} />
            <Stat label="Non verificabili" value={String(patterns.unverifiable_count ?? 0)} />
          </div>
          {extra ? (
            <p className="mt-2 text-[11px] text-slate-500">
              Statistiche squadra disponibili in {extra.prior_matches_with_stats ?? 0} partite su {extra.prior_matches ?? 0} dello storico.
            </p>
          ) : null}
          {groups.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">Nessun pattern senza quota acceso su questa partita.</p>
          ) : (
            <ul className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200">
              {visible.map((g) => {
                const f = g.first
                const isMarket = f.target_type === 'market'
                const open = openKey === g.key
                const bestRoi = isMarket ? Math.max(...g.patterns.map((x) => x.roi_pct ?? -Infinity)) : null
                const winRate = meanOf(g.patterns.map((x) => x.win_rate_pct))
                const deviation = meanOf(g.patterns.map((x) => x.avg_deviation_pct))
                const won = isMarket ? results[f.target_key]?.won : undefined
                return (
                  <li key={g.key} className="px-3 py-2.5">
                    <button type="button" onClick={() => setOpenKey(open ? null : g.key)} aria-expanded={open} className="flex w-full flex-wrap items-center justify-between gap-2 text-left">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-slate-900">
                          {isMarket ? (MARKET_LABELS[f.target_key] ?? f.market_label) : f.market_label}
                        </span>
                        <span className={isMarket ? todayBadgeActive : todayBadgeMuted}>{isMarket ? 'con quota' : 'senza quota'}</span>
                        <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[10px] font-semibold text-white">
                          {g.patterns.length} {g.patterns.length === 1 ? 'pattern' : 'pattern concordi'}
                        </span>
                        {won != null && <ResultCell won={won} />}
                      </span>
                      <span className="text-xs tabular-nums text-slate-600">
                        {isMarket
                          ? `ROI storico fino a ${signed(Number.isFinite(bestRoi) ? bestRoi : null)}${f.quota_book ? ` · quota oggi ${num(f.quota_book)}` : ''}`
                          : `riuscita storica ${num(winRate, 0)}% · scarto ${signed(deviation, 1, ' pt')}`}
                        <span className="ml-2 text-slate-400">{open ? '▴' : '▾'}</span>
                      </span>
                    </button>
                    {open && (
                      <ul className="mt-2 space-y-1.5 border-l-2 border-slate-200 pl-3">
                        {g.patterns.slice(0, PATTERNS_PER_GROUP_VISIBLE).map((x) => (
                          <li key={x.id} className="text-xs text-slate-600">
                            <span className="tabular-nums font-medium text-slate-800">
                              {isMarket ? `ROI ${signed(x.roi_pct)}` : `${num(x.win_rate_pct, 0)}%`} · {x.total_n} partite
                            </span>{' '}
                            — {x.conditions_text}
                          </li>
                        ))}
                        {g.patterns.length > PATTERNS_PER_GROUP_VISIBLE && (
                          <li className="text-xs text-slate-400">e altri {g.patterns.length - PATTERNS_PER_GROUP_VISIBLE} pattern con condizioni simili</li>
                        )}
                      </ul>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          {groups.length > PATTERN_GROUPS_VISIBLE && (
            <button type="button" onClick={() => setShowAll((s) => !s)} className="mt-2 text-xs font-medium text-slate-700 underline">
              {showAll ? 'Mostra meno' : `Mostra tutti i ${groups.length} segnali`}
            </button>
          )}
        </>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Scheda
// ---------------------------------------------------------------------------

export function CecchinoV25Panel({ todayFixtureId }: { todayFixtureId: number }) {
  const { data, error, loading } = useLiveFixture(todayFixtureId)
  if (loading) return <div className={`${todayCard} ${todayCardPadding} h-48 animate-pulse`} aria-busy="true" />
  if (error) return <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
  const p = data?.models['V2.5']
  if (!p || p.status === 'error' || !p.markets) {
    return (
      <div className={`${todayCard} ${todayCardPadding} text-sm text-slate-600`}>
        V2.5 non calcolabile per questa partita{p?.error ? `: ${p.error}` : '.'}
      </div>
    )
  }
  return (
    <div className="space-y-5">
      <section className={`${todayCard} ${todayCardPadding}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className={todaySectionTitle}>Cecchino V2.5</h3>
            <p className={todaySectionSubtitle}>
              Stessi moduli della V2 con i calcoli corretti · storico {p.modules?.history_matches ?? '—'} partite
            </p>
          </div>
          <SourceBadge p={p} />
        </div>
        {!p.eligible && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">Storico delle squadre sotto i minimi della RUN: numeri indicativi.</p>
        )}
      </section>
      <CecchinoPurchasabilityIndexV25 p={p} />
      <CecchinoPatternHero p={p} model="V2.5" hideWhenEmpty />
      <KpiPanel p={p} showPurchasability={false} />
      <BalancePanel p={p} />
      <GoalIntensityPanel p={p} />
      <PatternPanel p={p} />
    </div>
  )
}
