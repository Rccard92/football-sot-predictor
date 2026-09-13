import { useEffect, useState } from 'react'
import { PatternInsightsShell, Section } from '../components/pattern-insights/PatternInsightsShell'
import { MARKET_LABELS } from '../lib/cecchinoV3MatchesApi'
import { FAMILY_LABELS, INFORMATION_GROUP_LABELS } from '../lib/cecchinoV3EvaluatorApi'
import {
  CONDITION_LABELS,
  getFinalRuns,
  getPatternRuns,
  listPatterns,
  type FinalSummary,
  type PatternItem,
  type PatternRunSummary,
  type RateRow,
  type SimpleRun,
} from '../lib/cecchinoV3FinalApi'
import type { PlaySummary } from '../lib/cecchinoV3EvaluatorApi'

const TEXT_MUTED = 'var(--pi-muted)'
const COLOR_OK = '#1ea68f'
const COLOR_BAD = '#d95a57'
const LOCKBOX = '2025/2026'

function signed(v: number | null | undefined, d = 1, suffix = '%'): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(d)}${suffix}`
}

function pct(v: number | null | undefined, d = 1): string {
  return v == null ? '—' : `${(v * 100).toFixed(d)}%`
}

function Verdict({ passed, label }: { passed: boolean | null; label: string }) {
  if (passed == null) {
    return (
      <span className="whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ border: '1px solid var(--pi-border)' }}>
        — {label} (non disponibile)
      </span>
    )
  }
  const color = passed ? COLOR_OK : COLOR_BAD
  return (
    <span className="whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ border: `1px solid ${color}` }}>
      <span style={{ color }}>{passed ? '✓' : '✗'}</span> {label}
    </span>
  )
}

function RateCells({ r }: { r: RateRow | null | undefined }) {
  if (!r) return <td colSpan={4} style={{ color: TEXT_MUTED }}>non disponibile</td>
  return (
    <>
      <td className="tabular-nums">{r.tested.toLocaleString('it-IT')}</td>
      <td className="tabular-nums">
        {r.confirmed.toLocaleString('it-IT')} ({r.confirmed_rate_pct?.toFixed(1)}%)
      </td>
      <td className="tabular-nums">
        {r.expected.toLocaleString('it-IT')} ({r.expected_rate_pct?.toFixed(1)}%)
      </td>
      <td className="tabular-nums font-semibold">{r.lift?.toFixed(2) ?? '—'}</td>
    </>
  )
}

function PlayCells({ s }: { s: PlaySummary | undefined }) {
  if (!s || s.n === 0) return <td colSpan={4} style={{ color: TEXT_MUTED }}>nessuna giocata</td>
  return (
    <>
      <td className="tabular-nums">{s.n.toLocaleString('it-IT')}</td>
      <td className="tabular-nums">{pct(s.hit_rate)}</td>
      <td className="tabular-nums">{s.mean_odds?.toFixed(2)}</td>
      <td className="tabular-nums font-semibold">
        {signed(s.roi != null ? s.roi * 100 : null)}{' '}
        <span className="text-[10px] font-normal" style={{ color: TEXT_MUTED }}>
          ({signed(s.roi_low != null ? s.roi_low * 100 : null)} … {signed(s.roi_high != null ? s.roi_high * 100 : null)})
        </span>
      </td>
    </>
  )
}

function PatternComparison({ summary }: { summary: PatternRunSummary }) {
  const v3 = summary.patterns
  const v2 = summary.v2
  const seasons = v3.per_season.map((r) => r.season)
  return (
    <Section
      title="Pattern vincenti: V3 contro V2, stesso protocollo"
      note="Scoperta 2021/22 · confermato = ROI > 0 con almeno 20 giocate · caso = gruppi casuali di partite della stessa stagione"
    >
      <div className="mb-3 flex flex-wrap gap-2">
        <Verdict passed={summary.exam.P1} label="P1 conferme sopra il caso" />
        <Verdict passed={summary.exam.P2} label="P2 tenuta su 3 stagioni" />
        <Verdict passed={summary.exam.P3} label="P3 test congelato 2024/25 in utile" />
      </div>
      <div className="pi-scroll">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Stagione</th>
              <th>Modello</th>
              <th>Pattern verificati</th>
              <th>Confermati</th>
              <th>Attesi dal caso</th>
              <th>Rapporto (lift)</th>
            </tr>
          </thead>
          <tbody>
            {[...seasons, 'tutte'].flatMap((season) => {
              const r3 = season === 'tutte' ? v3.persistence : v3.per_season.find((r) => r.season === season)
              const r2 = season === 'tutte' ? v2?.persistence : v2?.per_season.find((r) => r.season === season)
              const label = season === 'tutte' ? 'Confermati in tutte e 3' : season
              return [
                <tr key={`${season}-v3`}>
                  <td className="font-semibold">{label}</td>
                  <td>V3</td>
                  <RateCells r={r3} />
                </tr>,
                <tr key={`${season}-v2`}>
                  <td />
                  <td>V2</td>
                  <RateCells r={r2} />
                </tr>,
              ]
            })}
          </tbody>
        </table>
      </div>
      <div className="pi-scroll mt-3">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Test congelato 2024/25</th>
              <th>Pattern</th>
              <th>Giocate (1 per partita e mercato)</th>
              <th>ROI</th>
              <th>ROI medio per pattern</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="font-semibold">V3</td>
              <td className="tabular-nums">{summary.frozen.patterns}</td>
              <td className="tabular-nums">{summary.frozen.bets.toLocaleString('it-IT')}</td>
              <td className="tabular-nums font-semibold">{signed(summary.frozen.roi_pct)}</td>
              <td className="tabular-nums">{signed(summary.frozen.pooled_roi_pct)}</td>
            </tr>
            <tr>
              <td className="font-semibold">V2</td>
              <td className="tabular-nums">{v2?.frozen?.patterns ?? '—'}</td>
              <td className="tabular-nums">{v2?.frozen?.union_reference.bets.toLocaleString('it-IT') ?? '—'}</td>
              <td className="tabular-nums font-semibold">{signed(v2?.frozen?.union_reference.roi_pct)}</td>
              <td className="tabular-nums">{signed(v2?.frozen?.pooled_roi_pct)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Section>
  )
}

function MarketMoveBlock({ summary, lockbox }: { summary: PatternRunSummary; lockbox: FinalSummary | null }) {
  const rows = [...summary.market_move.table, ...(lockbox?.market_move.table ?? [])]
  const open = summary.opening_plays
  return (
    <Section
      title="Il mercato si muove verso la V3?"
      note="Movimento dall'apertura alla chiusura spiegato dalla distanza V3 − apertura: beta 0 = nessun legame, 1 = la chiusura va dove dice la V3"
    >
      <div className="mb-3 flex flex-wrap gap-2">
        {summary.market_move.exam.map((e) => (
          <Verdict key={e.family} passed={e.passed} label={`M ${INFORMATION_GROUP_LABELS[e.family] ?? e.family}`} />
        ))}
      </div>
      <div className="pi-scroll">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Mercato</th>
              <th>Stagione</th>
              <th>Righe</th>
              <th>Beta e intervallo 95%</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.family}-${r.season}`}>
                <td className="font-semibold">{INFORMATION_GROUP_LABELS[r.family] ?? r.family}</td>
                <td>{r.season}</td>
                <td className="tabular-nums">{r.n.toLocaleString('it-IT')}</td>
                <td className="tabular-nums">
                  {r.beta == null ? '—' : `${r.beta.toFixed(3)} (${r.beta_low?.toFixed(3)} … ${r.beta_high?.toFixed(3)})`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pi-scroll mt-3">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Giocate V3 alla quota di apertura</th>
              <th>Giocate</th>
              <th>Vinte</th>
              <th>Quota media</th>
              <th>ROI all&apos;apertura</th>
              <th>Quota guadagnata sulla chiusura</th>
            </tr>
          </thead>
          <tbody>
            {[...open.by_season, { ...open.total, season: 'Totale' }].map((r) => (
              <tr key={r.season}>
                <td className="font-semibold">{r.season}</td>
                <PlayCells s={r} />
                <td className="tabular-nums">{signed(r.mean_odds_gain != null ? r.mean_odds_gain * 100 : null)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

function FinalBlock({ run }: { run: SimpleRun<FinalSummary> }) {
  const s = run.summary!
  const v3 = s.v3_patterns
  const lockTally = v3.tally.per_season[0]
  const families = ['FT_1X2', 'DOUBLE_CHANCE', 'FT_OVER_UNDER', 'HT_1X2']
  const seasons = Array.from(new Set(s.accuracy.map((r) => r.season)))
  return (
    <>
      <Section title="Test finale 2025/26 · verdetto" note="Stagione mai usata prima: tutto era congelato prima di questa misura">
        <div className="flex flex-wrap gap-2">
          <Verdict passed={s.exam.F0} label="F0 calcolo finale identico al modello" />
          <Verdict passed={s.exam.F1_available ? s.exam.F1 : null} label="F1 V3 piu' precisa della V2" />
          <Verdict passed={s.exam.F2} label="F2 pattern V3 vincenti" />
          <Verdict passed={s.exam.F3} label="F3 pattern V3 meglio della V2" />
        </div>
        <div className="mt-2 text-[11px]" style={{ color: TEXT_MUTED }}>
          Partite 2025/26 previste: {s.integrity.lockbox_matches.toLocaleString('it-IT')} · probabilita&apos; confrontate con il
          modello #5: {s.integrity.compared_probabilities.toLocaleString('it-IT')} · differenza massima{' '}
          {s.integrity.max_diff ?? '—'}
        </div>
      </Section>

      <Section title="Precisione per stagione: V3, V2 e book" note="Errore (Brier) sulle stesse partite · negativo = V3 migliore">
        <div className="pi-scroll">
          <table className="pi-table">
            <thead>
              <tr>
                <th>Stagione</th>
                <th>Famiglia</th>
                <th>Righe</th>
                <th>V3 vs V2</th>
                <th>V3 vs book</th>
                <th>V2 vs book</th>
              </tr>
            </thead>
            <tbody>
              {seasons.flatMap((season) =>
                families.map((family) => {
                  const r = s.accuracy.find((x) => x.season === season && x.family === family)
                  return (
                    <tr key={`${season}-${family}`}>
                      <td className={season === LOCKBOX ? 'font-semibold' : ''}>{season}</td>
                      <td>{FAMILY_LABELS[family] ?? family}</td>
                      <td className="tabular-nums">{r?.n.toLocaleString('it-IT') ?? '—'}</td>
                      <td className="tabular-nums font-semibold">{signed(r?.v3_vs_v2_pct, 2)}</td>
                      <td className="tabular-nums">{signed(r?.v3_vs_book_pct, 2)}</td>
                      <td className="tabular-nums">{signed(r?.v2_vs_book_pct, 2)}</td>
                    </tr>
                  )
                }),
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Pattern sul 2025/26: V3 contro V2" note="Pattern gia' scoperti e verificati, misurati per la prima volta sul 2025/26">
        <div className="pi-scroll">
          <table className="pi-table">
            <thead>
              <tr>
                <th>Modello</th>
                <th>Pattern verificati</th>
                <th>Confermati</th>
                <th>Attesi dal caso</th>
                <th>Lift</th>
                <th>Sempre confermati (22/23–24/25)</th>
                <th>ROI medio per giocata sul 2025/26</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="font-semibold">V3</td>
                <RateCells r={lockTally} />
                <td className="tabular-nums">{v3.always_confirmed.patterns}</td>
                <td className="tabular-nums font-semibold">{signed(v3.always_confirmed.pooled_roi_pct)}</td>
              </tr>
              <tr>
                <td className="font-semibold">V2</td>
                <RateCells r={s.v2_patterns?.tally} />
                <td className="tabular-nums">{s.v2_patterns?.always_confirmed.patterns ?? '—'}</td>
                <td className="tabular-nums font-semibold">{signed(s.v2_patterns?.always_confirmed.pooled_roi_pct)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="mt-2 text-[11px]" style={{ color: TEXT_MUTED }}>
          V3, pattern sempre confermati giocati sul 2025/26 con una giocata per partita e mercato:{' '}
          {v3.always_confirmed.bets.toLocaleString('it-IT')} giocate, ROI {signed(v3.always_confirmed.roi_pct)}.
        </div>
      </Section>

      <Section title="Valutatori sul 2025/26" note="Pesi stimati su 2021/22–2024/25">
        <div className="pi-scroll">
          <table className="pi-table">
            <thead>
              <tr>
                <th>Quota</th>
                <th>Strategia</th>
                <th>Giocate</th>
                <th>Vinte</th>
                <th>Quota media</th>
                <th>ROI (intervallo 95%)</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ['Chiusura', s.evaluator_closing],
                  ['Apertura', s.evaluator_opening],
                ] as const
              ).flatMap(([label, block]) => [
                <tr key={`${label}-main`}>
                  <td className="font-semibold">{label}</td>
                  <td>Valutatore</td>
                  <PlayCells s={block.VALUTATORE_PRINCIPALI} />
                </tr>,
                <tr key={`${label}-pure`}>
                  <td />
                  <td>V3 pura</td>
                  <PlayCells s={block.V3_PURA_PRINCIPALI} />
                </tr>,
              ])}
            </tbody>
          </table>
        </div>
      </Section>
    </>
  )
}

function PatternList() {
  const [only, setOnly] = useState<'' | 'confirmed_all' | 'frozen'>('confirmed_all')
  const [page, setPage] = useState(0)
  const [data, setData] = useState<{ total: number; items: PatternItem[] }>({ total: 0, items: [] })
  useEffect(() => {
    let alive = true
    listPatterns({ only, limit: 50, offset: page * 50 })
      .then((res) => alive && setData(res))
      .catch(() => alive && setData({ total: 0, items: [] }))
    return () => {
      alive = false
    }
  }, [only, page])
  const seasons = ['2022/2023', '2023/2024', '2024/2025']
  return (
    <Section title="Elenco pattern V3" note={`${data.total.toLocaleString('it-IT')} pattern con il filtro attuale`}>
      <div className="mb-3 flex flex-wrap gap-2">
        {(
          [
            ['confirmed_all', 'Confermati in tutte e 3 le stagioni'],
            ['frozen', 'Congelati (22/23 + 23/24)'],
            ['', 'Tutti'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key || 'all'}
            type="button"
            className="pi-btn"
            style={key === only ? { borderColor: COLOR_OK } : undefined}
            onClick={() => {
              setOnly(key)
              setPage(0)
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="pi-scroll" style={{ maxHeight: 560 }}>
        <table className="pi-table">
          <thead>
            <tr>
              <th>Mercato</th>
              <th>Condizioni</th>
              <th>Scoperta 21/22</th>
              {seasons.map((s) => (
                <th key={s}>{s}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.items.map((p) => (
              <tr key={p.id}>
                <td className="font-semibold">{MARKET_LABELS[p.market_key] ?? p.market_key}</td>
                <td>{p.conditions.map((c) => `${CONDITION_LABELS[c.column] ?? c.column} = ${c.value}`).join(' · ')}</td>
                <td className="whitespace-nowrap tabular-nums">
                  {p.discovery_n} · {signed(p.discovery_roi * 100)}
                </td>
                {seasons.map((s) => {
                  const r = p.seasons[s]
                  return (
                    <td key={s} className="whitespace-nowrap tabular-nums">
                      {!r || r.verdict === 'insufficient_sample'
                        ? '—'
                        : `${r.n} · ${signed(r.roi != null ? r.roi * 100 : null)}`}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-between text-[11px]" style={{ color: TEXT_MUTED }}>
        <button type="button" className="pi-btn" disabled={page === 0} onClick={() => setPage((x) => Math.max(0, x - 1))}>
          ← Precedenti
        </button>
        <span className="tabular-nums">pagina {page + 1}</span>
        <button type="button" className="pi-btn" disabled={(page + 1) * 50 >= data.total} onClick={() => setPage((x) => x + 1)}>
          Successivi →
        </button>
      </div>
    </Section>
  )
}

export function CecchinoV3FinalPage() {
  const [patternRun, setPatternRun] = useState<SimpleRun<PatternRunSummary> | null>(null)
  const [finalRun, setFinalRun] = useState<SimpleRun<FinalSummary> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([getPatternRuns(), getFinalRuns()])
      .then(([p, f]) => {
        if (!alive) return
        setPatternRun(p.completed)
        setFinalRun(f.completed)
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : 'Errore caricamento'))
    return () => {
      alive = false
    }
  }, [])

  return (
    <PatternInsightsShell>
      <header className="mb-5">
        <h1 className="text-xl font-bold tracking-tight">Cecchino V3 · Pattern e test finale</h1>
        <p className="mt-2 max-w-4xl text-xs leading-relaxed" style={{ color: TEXT_MUTED }}>
          La domanda finale: la V3 trova pattern vincenti meglio della V2? Stesso protocollo della V2 (scoperta sul 2021/22,
          verifica stagione per stagione contro il caso, test congelato) e poi un&apos;unica misura sulla stagione 2025/26,
          mai usata prima.
        </p>
      </header>
      {error && (
        <div className="mb-4 text-xs" style={{ color: '#fca5a5' }}>
          {error}
        </div>
      )}
      <div className="space-y-4">
        {finalRun?.summary && <FinalBlock run={finalRun} />}
        {patternRun?.summary && <PatternComparison summary={patternRun.summary} />}
        {patternRun?.summary && <MarketMoveBlock summary={patternRun.summary} lockbox={finalRun?.summary ?? null} />}
        {patternRun?.summary && <PatternList />}
        {!patternRun?.summary && !error && <div className="text-xs">Caricamento…</div>}
      </div>
    </PatternInsightsShell>
  )
}
