import { useCallback, useEffect, useState } from 'react'
import { PatternInsightsShell, Section } from '../components/pattern-insights/PatternInsightsShell'
import { MatchDetailPanel } from '../components/cecchino-v3/MatchDetailPanel'
import { MARKET_LABELS } from '../lib/cecchinoV3MatchesApi'
import {
  FAMILY_LABELS,
  INFORMATION_GROUP_LABELS,
  STRATEGY_LABELS,
  getEvaluatorRuns,
  listPlays,
  startEvaluatorRun,
  type EvaluatorPlay,
  type EvaluatorRun,
  type GroupedSummary,
  type PlaySummary,
  type StrategyCode,
} from '../lib/cecchinoV3EvaluatorApi'

const PAGE_SIZE = 50
const TEXT_MUTED = 'var(--pi-muted)'
const COLOR_OK = '#1ea68f'
const COLOR_BAD = '#d95a57'
const STRATEGIES: StrategyCode[] = ['VALUTATORE_PRINCIPALI', 'V3_PURA_PRINCIPALI', 'VALUTATORE_TUTTI']

function pct(v: number | null | undefined, d = 1): string {
  return v == null ? '—' : `${(v * 100).toFixed(d)}%`
}

function signedPct(v: number | null | undefined, d = 1): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${(v * 100).toFixed(d)}%`
}

function Verdict({ passed, label }: { passed: boolean; label?: string }) {
  const color = passed ? COLOR_OK : COLOR_BAD
  return (
    <span className="whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ border: `1px solid ${color}` }}>
      <span style={{ color }}>{passed ? '✓' : '✗'}</span> {label ?? (passed ? 'Superato' : 'Non superato')}
    </span>
  )
}

function SummaryCells({ s }: { s: PlaySummary }) {
  if (!s || s.n === 0) {
    return (
      <>
        <td className="tabular-nums">0</td>
        <td colSpan={6} style={{ color: TEXT_MUTED }}>
          nessuna giocata
        </td>
      </>
    )
  }
  return (
    <>
      <td className="tabular-nums">{s.n.toLocaleString('it-IT')}</td>
      <td className="tabular-nums">{pct(s.hit_rate)}</td>
      <td className="tabular-nums">{pct(s.mean_probability)}</td>
      <td className="tabular-nums">{pct(s.mean_book_probability)}</td>
      <td className="tabular-nums">{s.mean_odds?.toFixed(2)}</td>
      <td className="tabular-nums font-semibold">{signedPct(s.roi)}</td>
      <td className="whitespace-nowrap tabular-nums" style={{ color: TEXT_MUTED }}>
        {signedPct(s.roi_low)} … {signedPct(s.roi_high)}
      </td>
    </>
  )
}

const SUMMARY_HEADERS = (
  <>
    <th>Giocate</th>
    <th>Vinte</th>
    <th>Prob. media usata</th>
    <th>Prob. media book</th>
    <th>Quota media</th>
    <th>ROI</th>
    <th>Intervallo 95%</th>
  </>
)

function GroupTable({ title, rows, label }: { title: string; rows: GroupedSummary[]; label: (k: string) => string }) {
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider" style={{ color: TEXT_MUTED }}>
        {title}
      </div>
      <div className="pi-scroll">
        <table className="pi-table">
          <thead>
            <tr>
              <th />
              {SUMMARY_HEADERS}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td className="font-semibold">{label(r.key)}</td>
                <SummaryCells s={r} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function InformationBlock({ run }: { run: EvaluatorRun }) {
  const s = run.summary!
  const groups = Array.from(new Set(s.information.map((r) => r.group)))
  return (
    <Section
      title="Esame I · la V3 sa qualcosa che la quota non contiene?"
      note="Probabilita' del valutatore = book + V3, pesi stimati solo sulle stagioni precedenti · log-loss: piu' basso e' meglio"
    >
      <div className="mb-3 flex flex-wrap gap-2">
        {s.information_exam.map((e) => (
          <span key={e.family} className="flex items-center gap-2 text-xs">
            <span className="font-semibold">{INFORMATION_GROUP_LABELS[e.family] ?? e.family}</span>
            <Verdict passed={e.I1} label="I1 log-loss" />
            <Verdict passed={e.I2} label="I2 peso V3 > 0" />
          </span>
        ))}
      </div>
      <div className="pi-scroll">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Mercato</th>
              <th>Stagione</th>
              <th>Righe</th>
              <th>Log-loss book</th>
              <th>Log-loss V3</th>
              <th>Log-loss valutatore</th>
              <th>Guadagno sul book</th>
              <th>Peso V3 (c) e intervallo 95%</th>
            </tr>
          </thead>
          <tbody>
            {groups.flatMap((g) =>
              s.information
                .filter((r) => r.group === g)
                .map((r) => (
                  <tr key={`${g}-${r.season}`}>
                    <td className="font-semibold">{INFORMATION_GROUP_LABELS[g] ?? g}</td>
                    <td>{r.season}</td>
                    <td className="tabular-nums">{r.n.toLocaleString('it-IT')}</td>
                    <td className="tabular-nums">{r.ll_book?.toFixed(4) ?? '—'}</td>
                    <td className="tabular-nums">{r.ll_v3?.toFixed(4) ?? '—'}</td>
                    <td className="tabular-nums">{r.ll_valutatore?.toFixed(4) ?? '—'}</td>
                    <td className="tabular-nums">{r.gain_pct == null ? '—' : `${r.gain_pct > 0 ? '+' : ''}${r.gain_pct.toFixed(2)}%`}</td>
                    <td className="whitespace-nowrap tabular-nums">
                      {r.c == null ? '—' : `${r.c.toFixed(3)} (${r.c_low?.toFixed(3)} … ${r.c_high?.toFixed(3)})`}
                    </td>
                  </tr>
                )),
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-[10px]" style={{ color: TEXT_MUTED }}>
        Solo 1X2 finale e Over/Under 2.5 (quote di chiusura) fanno l&apos;esame; gli altri mercati usano l&apos;ultima quota
        rilevata e sono mostrati come confronto. La doppia chance ha gli stessi numeri dell&apos;1X2 perche&apos; ogni doppia
        chance e&apos; l&apos;esito opposto di un segno (1X = non 2).
      </div>
    </Section>
  )
}

function PlayabilityBlock({ run }: { run: EvaluatorRun }) {
  const exam = run.summary!.playability_exam
  return (
    <Section
      title="Esame G · giocabilita' alla quota di chiusura nei 16 campionati"
      note="Valore atteso >= 5%, quote 1,30-5,00, una giocata per partita, massimo 15 al giorno"
    >
      <div className="mb-3 flex flex-wrap gap-2">
        <Verdict passed={exam.G1} label="G1 ROI > 0 in ogni stagione" />
        <Verdict passed={exam.G2} label="G2 ROI sicuro sopra zero" />
        <Verdict passed={exam.G3} label="G3 almeno 300 giocate" />
      </div>
      <div className="pi-scroll">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Stagione</th>
              {SUMMARY_HEADERS}
            </tr>
          </thead>
          <tbody>
            {exam.by_season.map((r) => (
              <tr key={r.season}>
                <td className="font-semibold">{r.season}</td>
                <SummaryCells s={r} />
              </tr>
            ))}
            <tr>
              <td className="font-semibold">Totale</td>
              <SummaryCells s={exam.total} />
            </tr>
          </tbody>
        </table>
      </div>
    </Section>
  )
}

function StrategiesBlock({ run }: { run: EvaluatorRun }) {
  const s = run.summary!
  const [strategy, setStrategy] = useState<StrategyCode>('VALUTATORE_PRINCIPALI')
  const report = s.strategies[strategy]
  return (
    <Section title="Confronto delle strategie" note="Stagioni di giudizio 2022/23 – 2024/25">
      <div className="pi-scroll mb-4">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Strategia</th>
              {SUMMARY_HEADERS}
              <th>Giocate al giorno</th>
            </tr>
          </thead>
          <tbody>
            {STRATEGIES.map((code) => (
              <tr key={code}>
                <td className="font-semibold">{STRATEGY_LABELS[code]}</td>
                <SummaryCells s={s.strategies[code].total} />
                <td className="tabular-nums">{s.strategies[code].plays_per_day.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mb-3 flex flex-wrap gap-2">
        {STRATEGIES.map((code) => (
          <button
            key={code}
            type="button"
            className="pi-btn"
            style={code === strategy ? { borderColor: COLOR_OK } : undefined}
            onClick={() => setStrategy(code)}
          >
            {STRATEGY_LABELS[code]}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
        <GroupTable title="Per stagione" rows={report.by_season} label={(k) => k} />
        <GroupTable title="Per mercato" rows={report.by_market} label={(k) => MARKET_LABELS[k] ?? k} />
        <GroupTable title="Per famiglia" rows={report.by_family} label={(k) => FAMILY_LABELS[k] ?? k} />
        <GroupTable title="Per fascia di quota" rows={report.by_odds_band} label={(k) => k} />
        <GroupTable
          title="Per livello"
          rows={report.by_tier}
          label={(k) => (k === 'top' ? 'Prime divisioni' : k === 'lower' ? 'Divisioni inferiori' : k)}
        />
        <GroupTable
          title="Per fase"
          rows={report.by_phase}
          label={(k) => (k === 'final' ? 'Ultime 5 giornate' : k === 'mid' ? 'Stagione' : k)}
        />
        <GroupTable title="Per campionato" rows={report.by_competition} label={(k) => k} />
      </div>
    </Section>
  )
}

function EdgeGridBlock({ run }: { run: EvaluatorRun }) {
  const s = run.summary!
  return (
    <Section title="Soglia di valore (solo descrittivo)" note="Stessa strategia principale con soglie diverse: non si sceglie guardando qui">
      <div className="pi-scroll">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Valore atteso minimo</th>
              <th>Stagione</th>
              {SUMMARY_HEADERS}
            </tr>
          </thead>
          <tbody>
            {s.edge_grid.flatMap((g) => [
              ...g.by_season.map((r) => (
                <tr key={`${g.min_edge}-${r.season}`}>
                  <td>{pct(g.min_edge)}</td>
                  <td>{r.season}</td>
                  <SummaryCells s={r} />
                </tr>
              )),
              <tr key={`${g.min_edge}-tot`}>
                <td className="font-semibold">{pct(g.min_edge)}</td>
                <td className="font-semibold">Totale</td>
                <SummaryCells s={g.total} />
              </tr>,
            ])}
          </tbody>
        </table>
      </div>
      <div className="mt-3 text-[11px] font-semibold uppercase tracking-wider" style={{ color: TEXT_MUTED }}>
        Regola no-bet ultime 5 giornate
      </div>
      <div className="pi-scroll">
        <table className="pi-table">
          <thead>
            <tr>
              <th>Stagione</th>
              <th>Famiglia</th>
              <th>Righe di storico</th>
              <th>Guadagno log-loss del valutatore</th>
              <th>Ultime 5 giornate</th>
            </tr>
          </thead>
          <tbody>
            {s.final_phase_rules.map((r) => (
              <tr key={`${r.season}-${r.family}`}>
                <td>{r.season}</td>
                <td>{FAMILY_LABELS[r.family] ?? r.family}</td>
                <td className="tabular-nums">{r.n.toLocaleString('it-IT')}</td>
                <td className="tabular-nums">{r.gain == null ? 'storico insufficiente' : r.gain.toFixed(5)}</td>
                <td>{r.excluded ? 'no-bet' : 'giocabili'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

function PlaysBlock({ run, onOpen }: { run: EvaluatorRun; onOpen: (id: number) => void }) {
  const [strategy, setStrategy] = useState<StrategyCode>('VALUTATORE_PRINCIPALI')
  const [season, setSeason] = useState('')
  const [competition, setCompetition] = useState('')
  const [page, setPage] = useState(0)
  const [data, setData] = useState<{ total: number; items: EvaluatorPlay[]; competitions: string[] }>({
    total: 0,
    items: [],
    competitions: [],
  })
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    listPlays({ strategy, season, competition, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then((res) => alive && setData(res))
      .catch((e) => alive && setError(e instanceof Error ? e.message : 'Errore caricamento giocate'))
    return () => {
      alive = false
    }
  }, [run.id, strategy, season, competition, page])

  return (
    <Section title="Giocate" note={`${data.total.toLocaleString('it-IT')} giocate con i filtri attuali · clicca per il dettaglio partita`}>
      {error && (
        <div className="mb-2 text-xs" style={{ color: '#fca5a5' }}>
          {error}
        </div>
      )}
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
          Strategia
          <select
            className="pi-select"
            value={strategy}
            onChange={(e) => {
              setStrategy(e.target.value as StrategyCode)
              setPage(0)
            }}
          >
            {STRATEGIES.map((code) => (
              <option key={code} value={code}>
                {STRATEGY_LABELS[code]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
          Stagione
          <select
            className="pi-select"
            value={season}
            onChange={(e) => {
              setSeason(e.target.value)
              setPage(0)
            }}
          >
            <option value="">Tutte</option>
            {['2024/2025', '2023/2024', '2022/2023'].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
          Campionato
          <select
            className="pi-select"
            value={competition}
            onChange={(e) => {
              setCompetition(e.target.value)
              setPage(0)
            }}
          >
            <option value="">Tutti</option>
            {data.competitions.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="pi-scroll" style={{ maxHeight: 680 }}>
        <table className="pi-table">
          <thead>
            <tr>
              <th>Data</th>
              <th>Partita</th>
              <th>Mercato</th>
              <th>Quota</th>
              <th>Prob. V3</th>
              <th>Prob. book</th>
              <th>Prob. valutatore</th>
              <th>Valore atteso</th>
              <th>Esito</th>
              <th>Profitto</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((p) => (
              <tr key={`${p.lab_match_id}-${p.market_key}`} style={{ cursor: 'pointer' }} onClick={() => onOpen(p.lab_match_id)}>
                <td className="whitespace-nowrap tabular-nums">{new Date(p.match_date).toLocaleDateString('it-IT')}</td>
                <td>
                  <div className="font-semibold">
                    {p.home_team} – {p.away_team}
                  </div>
                  <div className="text-[10px]" style={{ color: TEXT_MUTED }}>
                    {p.competition} · {p.season_label}
                    {p.phase === 'final' ? ' · ultime 5 giornate' : ''}
                  </div>
                </td>
                <td className="font-semibold">{MARKET_LABELS[p.market_key] ?? p.market_key}</td>
                <td className="tabular-nums">{p.odds.toFixed(2)}</td>
                <td className="tabular-nums">{pct(p.p_v3)}</td>
                <td className="tabular-nums">{pct(p.p_book)}</td>
                <td className="tabular-nums">{pct(p.p_eval)}</td>
                <td className="tabular-nums">{signedPct(p.edge)}</td>
                <td>
                  <span style={{ color: p.won ? COLOR_OK : COLOR_BAD }}>{p.won ? '✓' : '✗'}</span>
                </td>
                <td className="tabular-nums">
                  {p.profit > 0 ? '+' : ''}
                  {p.profit.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-between text-[11px]" style={{ color: TEXT_MUTED }}>
        <button type="button" className="pi-btn" disabled={page === 0} onClick={() => setPage((x) => Math.max(0, x - 1))}>
          ← Precedenti
        </button>
        <span className="tabular-nums">
          {data.total === 0 ? 0 : page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.total)} di{' '}
          {data.total.toLocaleString('it-IT')}
        </span>
        <button
          type="button"
          className="pi-btn"
          disabled={(page + 1) * PAGE_SIZE >= data.total}
          onClick={() => setPage((x) => x + 1)}
        >
          Successivi →
        </button>
      </div>
    </Section>
  )
}

export function CecchinoV3EvaluatorPage() {
  const [runs, setRuns] = useState<{ latest: EvaluatorRun | null; completed: EvaluatorRun | null } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [detailId, setDetailId] = useState<number | null>(null)

  const loadRuns = useCallback(async () => {
    try {
      setRuns(await getEvaluatorRuns())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento')
    }
  }, [])

  useEffect(() => {
    let alive = true
    getEvaluatorRuns()
      .then((r) => alive && setRuns(r))
      .catch((e) => alive && setError(e instanceof Error ? e.message : 'Errore caricamento'))
    return () => {
      alive = false
    }
  }, [])

  const active = runs?.latest?.status === 'pending' || runs?.latest?.status === 'running'
  useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => void loadRuns(), 5000)
    return () => window.clearInterval(t)
  }, [active, loadRuns])

  const start = async () => {
    setBusy(true)
    try {
      await startEvaluatorRun()
      await loadRuns()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Avvio non riuscito')
    } finally {
      setBusy(false)
    }
  }

  const completed = runs?.completed?.summary ? runs.completed : null

  return (
    <PatternInsightsShell>
      <header className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight">Cecchino V3 · Valutatore di mercato</h1>
          {completed ? <span className="pi-chip">Modello di riferimento #{completed.source_run_id}</span> : null}
          {completed ? (
            <span className="pi-chip">{completed.summary!.matches.toLocaleString('it-IT')} partite</span>
          ) : null}
        </div>
        <p className="mt-2 max-w-4xl text-xs leading-relaxed" style={{ color: TEXT_MUTED }}>
          L&apos;unico punto in cui entrano le quote. Le probabilita&apos; degli agenti non cambiano: il valutatore misura se
          la V3 sa qualcosa che la quota non contiene e sceglie le giocate che, secondo questa misura, vincono piu&apos;
          spesso di quanto dica la quota. Tutto e&apos; stimato solo sulle stagioni precedenti; il 2025/26 resta chiuso.
        </p>
      </header>

      {error && (
        <div
          className="mb-4 rounded-xl border px-3 py-2 text-xs"
          style={{ borderColor: 'rgba(248,113,113,0.4)', background: 'rgba(248,113,113,0.08)', color: '#fca5a5' }}
        >
          {error}
        </div>
      )}

      <div className="space-y-4">
        <Section title="Calcolo" note={runs?.latest ? `Ultimo calcolo #${runs.latest.id}` : 'Nessun calcolo'}>
          {active ? (
            <div className="text-xs">{runs?.latest?.current_step ?? 'In attesa di avvio'}…</div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className="pi-btn" disabled={busy} onClick={() => void start()}>
                {completed ? 'Ricalcola valutatore' : 'Calcola valutatore'}
              </button>
              {runs?.latest?.status === 'failed' && (
                <span className="text-xs" style={{ color: '#fca5a5' }}>
                  Ultimo calcolo fallito: {runs.latest.error?.message ?? 'errore'}
                </span>
              )}
            </div>
          )}
        </Section>

        {completed && (
          <>
            <InformationBlock run={completed} />
            <PlayabilityBlock run={completed} />
            <StrategiesBlock run={completed} />
            <EdgeGridBlock run={completed} />
            <PlaysBlock run={completed} onOpen={setDetailId} />
          </>
        )}
      </div>

      {detailId != null && <MatchDetailPanel labMatchId={detailId} onClose={() => setDetailId(null)} />}
    </PatternInsightsShell>
  )
}
