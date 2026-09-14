import { useEffect, useState } from 'react'
import { MARKET_LABELS } from '../../lib/masterPatternApi'
import {
  getLiveFixture,
  type LiveFixtureResponse,
  type LiveModelPrediction,
  type LivePatternSignal,
} from '../../lib/cecchinoLiveApi'
import { formatFetchError } from '../../utils/formatFetchError'
import { todayBadgeActive, todayBadgeMuted, todayBadgeOk, todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

export type EngineTab = 'V2' | 'V2.5' | 'V3'

const TABS: { key: EngineTab; label: string; hint: string }[] = [
  { key: 'V2', label: 'V2', hint: 'Cecchino attuale' },
  { key: 'V2.5', label: 'V2.5', hint: 'Moduli corretti' },
  { key: 'V3', label: 'V3', hint: 'In arrivo' },
]

const MARKET_ORDER = [
  'HOME', 'DRAW', 'AWAY', 'ONE_X', 'X_TWO', 'ONE_TWO', 'HOME_PT', 'DRAW_PT', 'AWAY_PT',
  'OVER_0_5', 'UNDER_0_5', 'OVER_1_5', 'UNDER_1_5', 'OVER_2_5', 'UNDER_2_5', 'OVER_3_5', 'UNDER_3_5',
]

const CLASS_LABELS: Record<string, string> = {
  very_low: 'Molto bassa', low: 'Bassa', medium: 'Media', high: 'Alta', very_high: 'Molto alta',
  strong_balance: 'Equilibrio forte', balance: 'Equilibrio', transition: 'Transizione', imbalance: 'Squilibrio',
  very_weak: 'Molto debole', weak: 'Debole', moderate: 'Moderata', strong: 'Forte', very_strong: 'Molto forte',
  not_confirmed: 'Non confermata', partial: 'Parziale', confirmed: 'Confermata', strongly_confirmed: 'Fortemente confermata',
}

const BALANCE_PILLARS: [string, string][] = [
  ['f36', 'Equilibrio tra 1 e 2'],
  ['dominance', 'Convinzione del modello'],
  ['draw_credibility', 'Credibilità della X'],
  ['gap_coherence', 'Coerenza picchetti / modello gol'],
]

const GOAL_PILLARS: [string, string][] = [
  ['offensive_production', 'Produzione offensiva'],
  ['defensive_solidity', 'Solidità difensiva'],
  ['match_tempo', 'Ritmo partita'],
  ['offensive_stability', 'Stabilità offensiva'],
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

export function EngineTabBar({ value, onChange }: { value: EngineTab; onChange: (t: EngineTab) => void }) {
  return (
    <div role="tablist" aria-label="Motore di analisi" className="flex gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1">
      {TABS.map((t) => {
        const selected = t.key === value
        return (
          <button
            key={t.key}
            role="tab"
            type="button"
            aria-selected={selected}
            onClick={() => onChange(t.key)}
            className={`flex-1 rounded-lg px-3 py-2 text-left transition ${
              selected ? 'bg-white shadow-sm ring-1 ring-slate-200' : 'hover:bg-white/60'
            }`}
          >
            <div className={`text-sm font-semibold ${selected ? 'text-slate-900' : 'text-slate-600'}`}>{t.label}</div>
            <div className="text-[11px] text-slate-500">{t.hint}</div>
          </button>
        )
      })}
    </div>
  )
}

function useLiveFixture(todayFixtureId: number) {
  const [data, setData] = useState<LiveFixtureResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    getLiveFixture(todayFixtureId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(formatFetchError(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [todayFixtureId])
  return { data, error, loading }
}

function SourceBadge({ p }: { p: LiveModelPrediction }) {
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

type PatternGroupView = {
  key: string
  first: LivePatternSignal
  patterns: LivePatternSignal[]
}

/** Stesso mercato, linea e direzione = un solo segnale (come nell'osservazione live). */
function groupPatternSignals(patterns: LivePatternSignal[]): PatternGroupView[] {
  const map = new Map<string, PatternGroupView>()
  for (const p of patterns) {
    const key = `${p.target_type}|${p.target_key}|${p.threshold ?? ''}|${p.direction ?? 1}`
    const g = map.get(key)
    if (g) g.patterns.push(p)
    else map.set(key, { key, first: p, patterns: [p] })
  }
  return [...map.values()].sort(
    (a, b) =>
      Number(a.first.target_type !== 'market') - Number(b.first.target_type !== 'market') ||
      b.patterns.length - a.patterns.length,
  )
}

function meanOf(values: (number | null)[]): number | null {
  const v = values.filter((x): x is number => x != null)
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
}

const PATTERN_GROUPS_VISIBLE = 12
const PATTERNS_PER_GROUP_VISIBLE = 5

function PatternList({ patterns }: { patterns: LivePatternSignal[] }) {
  const [openKey, setOpenKey] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  if (patterns.length === 0) {
    return <p className="text-sm text-slate-500">Nessun pattern Master acceso su questa partita.</p>
  }
  const groups = groupPatternSignals(patterns)
  const visible = showAll ? groups : groups.slice(0, PATTERN_GROUPS_VISIBLE)
  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">
        {groups.length} {groups.length === 1 ? 'mercato' : 'mercati'} · i pattern sullo stesso mercato e linea contano come un solo segnale
      </p>
      <ul className="divide-y divide-slate-100">
        {visible.map((g) => {
          const p = g.first
          const isMarket = p.target_type === 'market'
          const open = openKey === g.key
          const bestRoi = isMarket ? Math.max(...g.patterns.map((x) => x.roi_pct ?? -Infinity)) : null
          const winRate = meanOf(g.patterns.map((x) => x.win_rate_pct))
          const deviation = meanOf(g.patterns.map((x) => x.avg_deviation_pct))
          return (
            <li key={g.key} className="py-2.5">
              <button
                type="button"
                onClick={() => setOpenKey(open ? null : g.key)}
                aria-expanded={open}
                className="flex w-full flex-wrap items-baseline justify-between gap-2 text-left"
              >
                <span className="text-sm font-semibold text-slate-900">
                  {isMarket ? (MARKET_LABELS[p.target_key] ?? p.market_label) : p.market_label}
                  <span className={`${todayBadgeActive} ml-2`}>
                    {g.patterns.length} {g.patterns.length === 1 ? 'pattern' : 'pattern concordi'}
                  </span>
                </span>
                <span className="text-xs tabular-nums text-slate-600">
                  {isMarket
                    ? `miglior ROI storico ${signed(Number.isFinite(bestRoi) ? bestRoi : null)}${p.quota_book ? ` · quota oggi ${num(p.quota_book)}` : ''}`
                    : `${num(winRate, 0)}% storico · scarto ${signed(deviation, 1, ' pt')}`}
                </span>
              </button>
              {open && (
                <ul className="mt-2 space-y-1.5 border-l-2 border-slate-100 pl-3">
                  {g.patterns.slice(0, PATTERNS_PER_GROUP_VISIBLE).map((x) => (
                    <li key={x.id} className="text-xs text-slate-600">
                      <span className="tabular-nums text-slate-800">
                        {isMarket ? `ROI ${signed(x.roi_pct)}` : `${num(x.win_rate_pct, 0)}%`} · {x.total_n} partite
                      </span>{' '}
                      — {x.conditions_text}
                    </li>
                  ))}
                  {g.patterns.length > PATTERNS_PER_GROUP_VISIBLE && (
                    <li className="text-xs text-slate-400">
                      e altri {g.patterns.length - PATTERNS_PER_GROUP_VISIBLE} pattern con condizioni simili
                    </li>
                  )}
                </ul>
              )}
            </li>
          )
        })}
      </ul>
      {groups.length > PATTERN_GROUPS_VISIBLE && (
        <button type="button" onClick={() => setShowAll((s) => !s)} className="mt-2 text-xs font-medium text-slate-700 underline">
          {showAll ? 'Mostra meno' : `Mostra tutti i ${groups.length} mercati`}
        </button>
      )}
    </div>
  )
}

function ClassGrid({ title, rows, values, final }: { title: string; rows: [string, string][]; values: Record<string, string | null> | null | undefined; final?: string | null }) {
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h4>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1.5 sm:grid-cols-2">
        {rows.map(([key, label]) => (
          <div key={key} className="flex justify-between gap-2 text-sm">
            <dt className="text-slate-600">{label}</dt>
            <dd className="font-medium text-slate-900">{cls(values?.[key])}</dd>
          </div>
        ))}
        {final !== undefined && (
          <div className="flex justify-between gap-2 text-sm sm:col-span-2">
            <dt className="text-slate-600">Intensità Goal complessiva</dt>
            <dd className="font-semibold text-slate-900">{cls(final)}</dd>
          </div>
        )}
      </dl>
    </div>
  )
}

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
  const markets = p.markets
  const results = p.result?.markets ?? {}
  const patterns = p.modules?.patterns
  const extra = patterns?.extra_stats
  return (
    <div className="space-y-5">
      <section className={`${todayCard} ${todayCardPadding}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className={todaySectionTitle}>Cecchino V2.5</h3>
            <p className={todaySectionSubtitle}>
              Probabilità normalizzate · valore contro il book senza margine · storico {p.modules?.history_matches ?? '—'} partite
            </p>
          </div>
          <SourceBadge p={p} />
        </div>
        {!p.eligible && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Storico delle squadre sotto i minimi della RUN: numeri indicativi.
          </p>
        )}
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                <th className="py-2 pr-2 font-medium">Mercato</th>
                <th className="py-2 pr-2 text-right font-medium">Prob.</th>
                <th className="py-2 pr-2 text-right font-medium">Quota Cecchino</th>
                <th className="py-2 pr-2 text-right font-medium">Quota book</th>
                <th className="py-2 pr-2 text-right font-medium">Vantaggio</th>
                <th className="py-2 pr-2 text-right font-medium">Valore atteso</th>
                <th className="py-2 pr-2 text-right font-medium">Rating</th>
                <th className="py-2 pr-2 font-medium">Acquistabilità</th>
                <th className="py-2 font-medium">Esito</th>
              </tr>
            </thead>
            <tbody>
              {MARKET_ORDER.filter((k) => markets[k]).map((k) => {
                const m = markets[k]
                const r = results[k]
                return (
                  <tr key={k} className="border-b border-slate-100 tabular-nums">
                    <td className="py-1.5 pr-2 font-medium text-slate-900">
                      {MARKET_LABELS[k] ?? k}
                      {m.signal_active && <span className={`${todayBadgeActive} ml-2`}>segnale</span>}
                    </td>
                    <td className="py-1.5 pr-2 text-right">{pct(m.probability)}</td>
                    <td className="py-1.5 pr-2 text-right">{num(m.quota_cecchino)}</td>
                    <td className="py-1.5 pr-2 text-right">{num(m.quota_book)}</td>
                    <td className="py-1.5 pr-2 text-right">{m.vantaggio_prob == null ? '—' : signed(m.vantaggio_prob * 100, 1, ' pt')}</td>
                    <td className="py-1.5 pr-2 text-right">{signed(m.edge_pct)}</td>
                    <td className="py-1.5 pr-2 text-right">{m.rating ?? '—'}</td>
                    <td className="py-1.5 pr-2 text-slate-700">{m.buyability_class ?? '—'}</td>
                    <td className="py-1.5 text-slate-700">{r?.won == null ? '—' : r.won ? 'Vinta' : 'Persa'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className={`${todayCard} ${todayCardPadding} grid gap-5 md:grid-cols-2`}>
        <ClassGrid title="Equilibrio vs Squilibrio" rows={BALANCE_PILLARS} values={p.modules?.balance_classes} />
        <ClassGrid title="Intensità Goal" rows={GOAL_PILLARS} values={p.modules?.goal_intensity_classes} final={p.modules?.goal_intensity_final ?? null} />
      </section>

      <section className={`${todayCard} ${todayCardPadding}`}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className={todaySectionTitle}>Pattern Master V2.5 accesi</h3>
          <span className="text-xs text-slate-500">In osservazione · nessuna giocata automatica</span>
        </div>
        {patterns?.status !== 'ok' ? (
          <p className="mt-2 text-sm text-slate-500">Pattern Master V2.5 non disponibili.</p>
        ) : (
          <>
            <p className="mt-1 text-xs text-slate-500">
              {patterns.active_count ?? 0} accesi su {patterns.patterns_total ?? 0} · {patterns.unverifiable_count ?? 0} non verificabili
              {extra ? ` (statistiche squadra in ${extra.prior_matches_with_stats ?? 0} partite su ${extra.prior_matches ?? 0} dello storico)` : ''}
            </p>
            <div className="mt-3">
              <PatternList patterns={patterns.active ?? []} />
            </div>
          </>
        )}
      </section>
    </div>
  )
}

export function CecchinoV3Panel() {
  return (
    <div className={`${todayCard} ${todayCardPadding}`}>
      <h3 className={todaySectionTitle}>Cecchino V3</h3>
      <p className="mt-2 text-sm text-slate-600">
        La V3 in live arriva dopo il collegamento automatico tra API-Football e il Lab (squadre, campionati e risultati della
        nuova stagione). Fino ad allora le sue previsioni non vengono calcolate né registrate.
      </p>
    </div>
  )
}
