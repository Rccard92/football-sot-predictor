import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AdminHttpError } from '../../lib/api'
import {
  getMatchStandings,
  getMatchTable,
  saveMatchNote,
  type MatchStandings,
  type MatchTableResponse,
  type MatchTableRow,
  type Reliability,
  type Remaining,
  type StandingsKind,
  type TableQuote,
  type TableBlock,
  type TableGame,
  type TableOutcome,
} from '../../lib/analystJournalApi'
import { getCecchinoTodayDetail, type CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { CecchinoTodayKpiPanel } from '../cecchino/CecchinoTodayKpiPanel'
import { todayCard, todayCardPadding } from '../cecchino/cecchinoTodayStyles'
import { JournalDialog } from './AddToJournalButton'
import { ClassPill, ContextSection, FiveBoxes, FormBlock, HeaderAlerts, HeaderTypeLine, SaveButton, SignsTable } from './DiarioScheda'
import { C, OUTCOME_FILL } from './diarioFormat'

/** Tabella analisi (bozza di Giovanni, 05/11/2026; grafica rifatta il 05/11): lista compatta delle partite con
 *  la forma a quadratini, e scheda della partita scelta con il dettaglio, il pannello KPI, il diario e le note.
 *  Il giro del mattino scansiona anche domani, quindi qui si preparano oggi le partite di domani.
 *  06/11 (richieste di Giovanni): risultato dentro il quadratino, cornice anche sui pareggi, gol PT e FT in ogni
 *  blocco, media dei gialli, classifica completa (totale, casa, trasferta), indicatore di equilibrio tolto.
 *  07/11: solo partite calcolate da Cecchino; quote colorate con le regole di acquisto (verde si compra, rosso fuori
 *  fascia, barrata da evitare); tipo di partita Equilibrio / Squilibrio / Scala dalle quote 1-X-2 (solo qui).
 *  09/11 (documento "Modifiche" di Giovanni, regola: aggiungere, non togliere): numero +/- sotto ogni risultato
 *  (differenza punti alla data della gara), cornice da +3, nome e data dell'avversaria, forza media, gol e segni,
 *  casa/fuori una sotto l'altra (PT poi finale) e forma totale con lo stesso schema, note in fondo; solo gare della
 *  stagione in corso; "forma da gol" in arancione su Under 2,5 e Under 1,5 PT; partita non editabile con meno di 3 gare. */

const btn = 'rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[13px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60'
const selectClass = 'rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm'
const LABEL = 'text-[12px] text-slate-500'
const SQUARE: Record<TableOutcome, string> = {
  V: 'bg-emerald-100 text-emerald-800',
  N: 'bg-slate-100 text-slate-500',
  P: 'bg-rose-100 text-rose-800',
}
const OUTCOME_WORD: Record<TableOutcome, string> = { V: 'vinta', N: 'pareggiata', P: 'persa' }
const MAIN_QUOTES = ['HOME', 'DRAW', 'AWAY']
function quoteTitle(q: TableQuote | undefined): string | undefined {
  if (!q) return undefined
  const cecchino = q.quota_cecchino ? `Quota Cecchino ${quoteText(q.quota_cecchino)}` : ''
  const why = q.warnings?.length ? q.warnings.join(' · ') : q.status === 'ok' ? 'Dentro le regole di acquisto' : ''
  return [why, cecchino].filter(Boolean).join(' — ') || undefined
}

type Order = 'time' | 'league'
const WIDE_QUERY = '(min-width: 1280px)'

/** Schermo largo: scheda accanto alla lista; altrimenti la scheda si apre in un riquadro. */
function useIsWide(): boolean {
  const query = useMemo(
    () => (typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(WIDE_QUERY) : null),
    [],
  )
  const [wide, setWide] = useState(query ? query.matches : true)
  useEffect(() => {
    if (!query) return
    const onChange = (e: MediaQueryListEvent) => setWide(e.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [query])
  return wide
}

function romeDate(offsetDays = 0): string {
  const d = new Date(Date.now() + offsetDays * 86400000)
  return d.toLocaleDateString('sv-SE', { timeZone: 'Europe/Rome' })
}

function kickoffTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' })
}

function dayLabel(day: string): string {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' })
}

function errorText(e: unknown): string {
  return e instanceof AdminHttpError ? e.message : e instanceof Error ? e.message : 'Errore'
}

function quoteText(q: number | null | undefined): string {
  return q == null ? '—' : q.toFixed(2).replace('.', ',')
}

/** +5, 0, −3 (segno meno tipografico) */
function signed(v: number): string {
  return v > 0 ? `+${v}` : v < 0 ? `−${Math.abs(v)}` : '0'
}

/** punti a partita con due decimali e il segno: +0,45, −1,20, 0,00 (18/11/2026) */
function ppgText(v: number): string {
  const text = Math.abs(v).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v > 0 ? `+${text}` : v < 0 ? `−${text}` : text
}

function shortDate(iso: string | null): string {
  return iso ? new Date(`${iso}T12:00:00Z`).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }) : ''
}

function gameTitle(g: TableGame, half: 'PT' | 'FT'): string {
  const outcome = half === 'PT' ? g.ht_outcome : g.ft_outcome
  const score = half === 'PT' ? g.ht : g.ft
  const rank = g.opponent_rank ? ` (oggi ${g.opponent_rank}ª)` : ''
  const diff = g.diff != null ? ` · ${ppgText(g.diff)} punti a partita alla data${g.diff_points != null ? ` (${signed(g.diff_points)} punti)` : ''}` : ''
  return `${shortDate(g.date)} ${g.home ? 'in casa con' : 'fuori con'} ${g.opponent ?? '?'}${rank}: ${score ?? '—'} ${half}${outcome ? `, ${OUTCOME_WORD[outcome]}` : ''}${diff}`
}

/** Gara rinviata o spostata rispetto alla fotografia del mattino (18/11/2026). */
function movedLabel(moved: NonNullable<MatchTableRow['moved']>): string {
  if (moved.status === 'CANC') return 'annullata'
  if (moved.status === 'ABD') return 'sospesa'
  if (moved.status === 'moved' && moved.kickoff) {
    return `spostata al ${new Date(moved.kickoff).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', timeZone: 'Europe/Rome' })}`
  }
  return 'rinviata'
}

/** Gare di campionato che mancano, compresa questa: esatte dal calendario o stimate (18/11/2026). */
function remainingText(team: string, r: Remaining | null | undefined): string | null {
  if (!r) return null
  if (r.phase === 'knockout') return null
  if (r.phase === 'end') return `${team}: stagione regolare finita`
  if (r.exact) return `${team}: ${r.games === 1 ? 'manca 1 gara' : `mancano ${r.games} gare`}`
  return `${team}: circa ${r.games} ${r.games === 1 ? 'gara' : 'gare'}`
}

const ESTIMATE_NOTE = 'Stima: gare di campionato per squadra nella stagione precedente meno quelle giocate (nel nostro archivio manca il calendario)'

function RemainingInfo({
  homeTeam,
  awayTeam,
  home,
  away,
  className,
}: {
  homeTeam: string
  awayTeam: string
  home: Remaining | null | undefined
  away: Remaining | null | undefined
  className: string
}) {
  if (home?.phase === 'knockout' || away?.phase === 'knockout') {
    return <p className={className}>Fase finale · gara a eliminazione diretta</p>
  }
  const texts = [remainingText(homeTeam, home), remainingText(awayTeam, away)].filter(Boolean)
  if (!texts.length) return null
  const estimated = [home, away].some((x) => x && !x.exact && !x.phase)
  return (
    <p className={className} title={estimated ? ESTIMATE_NOTE : 'Dal calendario del campionato'}>
      Fine campionato · {texts.join(' · ')}
      {estimated ? ' (stima)' : ''}
    </p>
  )
}

function RemainingLine({ row }: { row: MatchTableRow }) {
  return (
    <RemainingInfo
      homeTeam={row.home_team}
      awayTeam={row.away_team}
      home={row.remaining?.home}
      away={row.remaining?.away}
      className="mt-1 text-[12px] text-slate-500"
    />
  )
}

/** Forma nella lista (modifica 14): 5 quadratini colorati dall'esito e i punti; le cifre ±forza sono nella scheda. */
function ListSquares({ block }: { block: TableBlock }) {
  if (!block.enough) return <span className="text-[12px] text-slate-400" title={`Solo ${block.games} gare`}>—</span>
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span className="inline-flex gap-0.5">
        {block.results.map((g, i) => (
          <span
            key={i}
            title={gameTitle(g, 'FT')}
            className="inline-block h-3 w-3 rounded-[3px]"
            style={{ background: g.ft_outcome ? OUTCOME_FILL[g.ft_outcome] : '#E5E7EB' }}
          />
        ))}
      </span>
      <span className="w-5 text-[13px] font-semibold tabular-nums text-slate-900">{block.points}</span>
    </span>
  )
}

function ListRow({ row, selected, onSelect, showLeague }: { row: MatchTableRow; selected: boolean; onSelect: () => void; showLeague: boolean }) {
  const main = MAIN_QUOTES.map((k) => row.quotes.find((q) => q.key === k))
  const counts = row.evaluation?.counts
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`grid w-full grid-cols-[48px_minmax(0,1fr)] gap-x-3 gap-y-1.5 border-b border-slate-100 px-3 py-2.5 text-left text-[13px] transition sm:grid-cols-[48px_minmax(0,1fr)_auto_64px_110px] ${
        selected ? 'border-l-4 border-l-[#2457B3] bg-[#E3EDFF]/60' : 'hover:bg-slate-50'
      } ${row.started ? 'opacity-70' : ''}`}
      aria-pressed={selected}
    >
      <span className="pt-0.5 text-[15px] font-semibold tabular-nums text-slate-900">{kickoffTime(row.kickoff)}</span>
      <span className="min-w-0">
        <span className="flex items-center gap-1.5 font-semibold text-slate-900">
          <ReliabilityDot r={row.reliability} />
          <span className="min-w-0">
            {row.home_team}
            {row.home_rank ? <span className="ml-1 text-[12px] font-normal text-slate-400">{row.home_rank}ª</span> : null}
            <span className="mx-1 text-slate-300">–</span>
            {row.away_team}
            {row.away_rank ? <span className="ml-1 text-[12px] font-normal text-slate-400">{row.away_rank}ª</span> : null}
          </span>
        </span>
        <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
          {showLeague ? <span className="truncate text-[12px] text-slate-500">{row.league}</span> : null}
          {row.weather?.kickoff ? (
            <span className="text-[12px]" title={`Meteo al via: ${row.weather.kickoff.text}`}>
              · {row.weather.kickoff.icon}
            </span>
          ) : null}
          {row.match_type ? (
            <ClassPill cls={row.match_type} title="Tipo partita dalle quote Bet365 e indice di equilibrio Cecchino (0-100)">
              {row.match_type}
            </ClassPill>
          ) : null}
          {row.balance?.index != null ? <span className="text-[12px] tabular-nums text-slate-500">{Math.round(row.balance.index)}</span> : null}
          {row.my_note.trim() ? <span className="text-[12px] text-indigo-700" title="Hai scritto una nota">● nota</span> : null}
          {row.started ? <span className="text-[12px] text-slate-400">iniziata</span> : null}
          {row.data_check?.level === 'red' ? (
            <span className="rounded bg-rose-100 px-1.5 text-[12px] font-medium text-rose-800" title={row.data_check.problems.join(' · ')}>
              dati da verificare
            </span>
          ) : null}
          {row.moved ? <span className="rounded bg-slate-100 px-1.5 text-[12px] text-slate-600">{movedLabel(row.moved)}</span> : null}
        </span>
      </span>
      <span className="col-start-2 flex flex-col gap-1 sm:col-start-auto">
        <ListSquares block={row.blocks.forma_casa} />
        <ListSquares block={row.blocks.forma_fuori} />
      </span>
      <span className="col-start-2 self-center whitespace-nowrap text-[13px] font-semibold tabular-nums sm:col-start-auto" title="Segni giocabili o da verificare ✓ · bloccati ✕">
        {counts ? (
          <>
            <span style={{ color: C.win.text }}>{counts.playable + counts.check} ✓</span>{' '}
            <span style={{ color: C.loss.text }}>{counts.blocked} ✕</span>
          </>
        ) : (
          <span className="text-slate-400">n.d.</span>
        )}
      </span>
      <span className="col-start-2 self-center whitespace-nowrap text-right tabular-nums text-slate-700 sm:col-start-auto" title={main.map(quoteTitle).filter(Boolean).join(' · ') || undefined}>
        {main.map((q) => quoteText(q?.quota)).join(' · ')}
      </span>
    </button>
  )
}

/** Legenda della scheda (capitolato del 24/11/2026: si chiude nel contesto, il testo resta). */
function FormNotes() {
  return (
    <ul className="list-disc space-y-0.5 pl-4 text-[13px] text-slate-700">
      <li>
        <b>Q</b> = la quota usata dalle regole: la seconda lettura Bet365 (75&apos; prima del via) se c&apos;è, altrimenti quella del mattino. Stati, colori, R1,
        valore e conteggi si calcolano su Q; le giocate già salvate non cambiano.
      </li>
      <li>
        <b>Quattro stati</b>: giocabile (quota nella fascia, nessuna regola di blocco); da verificare (valore Cecchino sopra +30%: di solito è un errore del
        modello); bloccato (R1, R2 o regole del sito, sempre con il motivo); fuori fascia (nascosto dietro «altri N segni»).
      </li>
      <li>
        <b>R1</b> = Q sotto la quota Cecchino × 0,90. <b>R2</b> = su Over PT 0,5 almeno 3 volte 0-0 al PT nelle ultime 5 in casa (blocca); su 1 e 1X casa
        sotto 4 punti su 15 in casa (per ora solo avviso: sullo storico i segni tolti rendevano meglio).
      </li>
      <li>
        <b>Forma</b>: colore pieno = esito (verde vinta, grigio pari, rosso persa); cornice tratteggiata = il risultato cambia dal PT al finale; ▲ ● ▼ =
        avversaria più forte, alla pari o più debole di almeno 0,3 punti a partita alla data (il numero è al passaggio del mouse).
      </li>
      <li>
        <b>Affidabilità</b>: pallino verde (tutto a posto), giallo (solo da leggere), rosso (gara esclusa). Solo i campionati ammessi.
      </li>
      <li>
        <b>Solo stagione in corso.</b> Meno di 3 gare in casa e 3 fuori = gara non editabile.
      </li>
      <li>
        <b>Avviso Under</b>: sopra 2,7 gol a gara (casa della squadra di casa e fuori dell&apos;ospite). <b>Avviso PT</b>: sopra 1,5 gol del primo tempo a
        gara.
      </li>
      <li>
        <b>Avvisi di calendario e motivazione</b> (gialli, nella testata): solo informazione, non cambiano nessuno stato.
      </li>
      <li>Dato non noto = «n.d.», mai 0. Accanto a ogni dato che cambia nel tempo c&apos;è l&apos;ora della lettura.</li>
    </ul>
  )
}

const RELIABILITY_STYLE: Record<Reliability['level'], { label: string; box: string; dot: string; note: string }> = {
  green: {
    label: 'Verde · gara analizzabile',
    box: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    dot: 'bg-emerald-500',
    note: 'Squadre verificate, classifica completa, quote recenti, ammonizioni presenti.',
  },
  yellow: { label: 'Giallo · solo da leggere', box: 'border-amber-200 bg-amber-50 text-amber-900', dot: 'bg-amber-400', note: '' },
  red: { label: 'Rosso · gara esclusa', box: 'border-rose-200 bg-rose-50 text-rose-900', dot: 'bg-rose-500', note: '' },
}

function ReliabilityDot({ r }: { r?: Reliability }) {
  if (!r) return null
  const s = RELIABILITY_STYLE[r.level]
  return <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${s.dot}`} title={[s.label, ...r.red, ...r.yellow].join(' · ')} aria-label={s.label} />
}

/** Note dell'analista: si salvano da sole poco dopo aver smesso di scrivere e quando si cambia partita. */
function NoteEditor({ row, canWrite, onSaved }: { row: MatchTableRow; canWrite: boolean; onSaved: (id: number, note: string) => void }) {
  const [text, setText] = useState(row.my_note)
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const last = useRef(row.my_note)
  const pending = useRef(row.my_note)

  const save = useCallback(
    (value: string) => {
      if (value === last.current) return
      setState('saving')
      saveMatchNote(row.today_fixture_id, value).then(
        () => {
          last.current = value
          onSaved(row.today_fixture_id, value)
          setState('saved')
        },
        () => setState('error'),
      )
    },
    [row.today_fixture_id, onSaved],
  )

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
      if (pending.current !== last.current) {
        const id = row.today_fixture_id
        const value = pending.current
        void saveMatchNote(id, value).then(() => onSaved(id, value), () => undefined)
      }
    },
    [row.today_fixture_id, onSaved],
  )

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className={LABEL}>Note analista</p>
        <p className="text-[12px] text-slate-400">
          {state === 'saving' ? 'Salvo…' : state === 'saved' ? 'Salvata' : state === 'error' ? <span className="text-rose-600">Non salvata, riprova</span> : ''}
        </p>
      </div>
      <textarea
        className="mt-1 h-32 w-full resize-y rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none disabled:bg-slate-50"
        placeholder={canWrite ? 'Cosa ti dice questa partita?' : 'Serve un account per scrivere'}
        value={text}
        disabled={!canWrite}
        onChange={(e) => {
          const value = e.target.value
          setText(value)
          pending.current = value
          setState('idle')
          if (timer.current) clearTimeout(timer.current)
          timer.current = setTimeout(() => save(value), 800)
        }}
        onBlur={() => {
          if (timer.current) clearTimeout(timer.current)
          save(text)
        }}
      />
      {row.other_notes.map((n, i) => (
        <p key={i} className="mt-1.5 rounded-lg bg-slate-50 px-2.5 py-1.5 text-[13px] text-slate-600">
          <span className="font-medium">{n.user_name ?? 'Analista'}:</span> {n.note}
        </p>
      ))}
    </div>
  )
}

/** Pannello KPI della partita, lo stesso di Cecchino Today, in un riquadro laterale. */
function KpiDrawer({ row, onClose }: { row: MatchTableRow; onClose: () => void }) {
  const [detail, setDetail] = useState<CecchinoTodayDetailResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    getCecchinoTodayDetail(row.today_fixture_id).then(
      (d) => {
        if (alive) setDetail(d)
      },
      (e: unknown) => {
        if (alive) setError(errorText(e))
      },
    )
    return () => {
      alive = false
    }
  }, [row.today_fixture_id])
  const panel = detail ? (detail.kpi_panel_v2 ?? detail.kpi_panel) : null
  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-slate-900/40" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="h-full w-full max-w-3xl space-y-4 overflow-y-auto bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[13px] text-slate-500">
              {kickoffTime(row.kickoff)} · {row.country} · {row.league}
            </p>
            <h2 className="text-base font-semibold text-slate-900">
              {row.home_team} – {row.away_team}
            </h2>
          </div>
          <button type="button" className={btn} onClick={onClose}>
            Chiudi
          </button>
        </div>
        {error ? <p className="text-sm text-rose-700">{error}</p> : null}
        {!detail && !error ? <p className="text-sm text-slate-500">Carico il pannello KPI…</p> : null}
        {detail && detail.status !== 'ok' ? <p className="text-sm text-slate-600">{detail.message ?? 'Pannello KPI non disponibile per questa partita.'}</p> : null}
        {detail && detail.status === 'ok' && panel ? (
          <CecchinoTodayKpiPanel
            panel={panel}
            bookmakerStatus={panel.bookmaker_status}
            todayFixtureId={detail.today_fixture_id ?? detail.id}
            providerFixtureId={detail.provider_fixture_id}
          />
        ) : null}
        {detail && detail.status === 'ok' && !panel ? <p className="text-sm text-slate-600">Pannello KPI non disponibile per questa partita.</p> : null}
      </aside>
    </div>
  )
}

const STANDINGS_TABS: [StandingsKind, string][] = [
  ['total', 'Totale'],
  ['home', 'Casa'],
  ['away', 'Trasferta'],
]

/** Classifica completa del campionato, ricostruita dai risultati: totale, solo casa, solo trasferta.
 *  08/11/2026: un clic su una delle due squadre della partita accende le avversarie delle sue ultime 5 gare
 *  (in casa, fuori o in totale, come la scheda aperta) con il colore del risultato, e sotto compare il box
 *  con quelle partite. La posizione dell'avversaria nel box e' quella della classifica totale. */
const SCOPE_WORDS: Record<StandingsKind, string> = { total: 'partite', home: 'partite in casa', away: 'partite fuori casa' }
const ROW_TINT: Record<TableOutcome, string> = { V: 'bg-emerald-50', N: 'bg-slate-100', P: 'bg-rose-50' }

function StandingsDrawer({ row, onClose }: { row: MatchTableRow; onClose: () => void }) {
  const [data, setData] = useState<MatchStandings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [kind, setKind] = useState<StandingsKind>('total')
  const [selected, setSelected] = useState<number | null>(null)
  useEffect(() => {
    let alive = true
    getMatchStandings(row.today_fixture_id).then(
      (d) => {
        if (alive) setData(d)
      },
      (e: unknown) => {
        if (alive) setError(errorText(e))
      },
    )
    return () => {
      alive = false
    }
  }, [row.today_fixture_id])
  const rows = data?.tables[kind] ?? []
  const playing = data ? [data.home_team_id, data.away_team_id] : []
  const games = useMemo(() => (data && selected !== null ? (data.recent?.[String(selected)]?.[kind] ?? []) : []), [data, selected, kind])
  const byOpponent = useMemo(() => {
    const out = new Map<number, TableGame[]>()
    for (const g of games) if (g.opponent_id != null) out.set(g.opponent_id, [...(out.get(g.opponent_id) ?? []), g])
    return out
  }, [games])
  const teamName = (id: number | null) => (id === null ? '' : (data?.tables.total.find((r) => r.team_id === id)?.team ?? (id === data?.home_team_id ? row.home_team : row.away_team)))

  const rowClass = (id: number) => {
    if (selected !== null) {
      if (id === selected) return 'bg-indigo-100 font-semibold text-slate-900'
      const met = byOpponent.get(id)
      if (met) return `${ROW_TINT[met[met.length - 1].ft_outcome ?? 'N']} font-medium text-slate-900`
      return 'text-slate-400'
    }
    return playing.includes(id) ? 'bg-indigo-50 font-semibold text-slate-900' : 'text-slate-700'
  }

  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-slate-900/40" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="h-full w-full max-w-2xl space-y-4 overflow-y-auto bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[13px] text-slate-500">
              Classifica · {row.country} · {row.league}
            </p>
            <h2 className="text-base font-semibold text-slate-900">
              {row.home_team} – {row.away_team}
            </h2>
          </div>
          <button type="button" className={btn} onClick={onClose}>
            Chiudi
          </button>
        </div>
        <div className="inline-flex overflow-hidden rounded-lg border border-slate-200" role="group" aria-label="Classifica">
          {STANDINGS_TABS.map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              className={`px-3 py-1.5 text-sm font-medium ${kind === k ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 hover:bg-slate-50'}`}
            >
              {label}
            </button>
          ))}
        </div>
        {error ? <p className="text-sm text-rose-700">{error}</p> : null}
        {!data && !error ? <p className="text-sm text-slate-500">Carico la classifica…</p> : null}
        {data ? (
          <>
            <p className="text-[13px] text-slate-500">
              {selected === null
                ? `Clicca su ${row.home_team} o ${row.away_team} per vedere contro chi hanno giocato le ultime 5 ${SCOPE_WORDS[kind]}.`
                : `${teamName(selected)}: avversarie delle ultime 5 ${SCOPE_WORDS[kind]}, colorate con il risultato (verde vinta, grigio pari, rosso persa). Clicca di nuovo per togliere.`}
            </p>
            <table className="w-full text-[13px] tabular-nums">
              <thead>
                <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-400">
                  <th className="py-1.5 pl-1 pr-2 text-left font-semibold">#</th>
                  <th className="py-1.5 pr-2 text-left font-semibold">Squadra</th>
                  {['G', 'V', 'N', 'P', 'GF', 'GS', 'DR', 'Pt'].map((h) => (
                    <th key={h} className="px-1 py-1.5 text-right font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const met = selected !== null ? byOpponent.get(r.team_id) : undefined
                  const clickable = playing.includes(r.team_id)
                  return (
                    <tr key={r.team_id} className={`border-b border-slate-100 ${rowClass(r.team_id)}`}>
                      <td className="py-1.5 pl-1 pr-2">{r.rank}</td>
                      <td className="py-1.5 pr-2">
                        {clickable ? (
                          <button
                            type="button"
                            onClick={() => setSelected((s) => (s === r.team_id ? null : r.team_id))}
                            aria-pressed={selected === r.team_id}
                            className="font-semibold text-indigo-800 underline decoration-dotted underline-offset-2 hover:text-indigo-950"
                          >
                            {r.team ?? '—'}
                          </button>
                        ) : (
                          r.team ?? '—'
                        )}
                        {met?.map((g, i) => (
                          <span
                            key={i}
                            title={gameTitle(g, 'FT')}
                            className={`ml-1.5 inline-flex h-5 min-w-[2rem] items-center justify-center rounded px-0.5 text-[11px] font-semibold ${g.ft_outcome ? SQUARE[g.ft_outcome] : 'bg-slate-50 text-slate-300'}`}
                          >
                            {g.ft ?? '·'}
                          </span>
                        ))}
                      </td>
                      <td className="px-1 py-1.5 text-right">{r.played}</td>
                      <td className="px-1 py-1.5 text-right">{r.won}</td>
                      <td className="px-1 py-1.5 text-right">{r.drawn}</td>
                      <td className="px-1 py-1.5 text-right">{r.lost}</td>
                      <td className="px-1 py-1.5 text-right">{r.gf}</td>
                      <td className="px-1 py-1.5 text-right">{r.ga}</td>
                      <td className="px-1 py-1.5 text-right">{r.gd > 0 ? `+${r.gd}` : r.gd}</td>
                      <td className="px-1 py-1.5 text-right font-semibold text-slate-900">{r.points}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="text-[12px] text-slate-500">
              {data.as_of
                ? `Classifica prima della gara (${new Date(data.as_of).toLocaleString('it-IT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' })}), ricostruita`
                : 'Ricostruita'}{' '}
              dai {data.games} risultati del campionato nel nostro archivio.
              {!data.complete ? ' Mancano alcuni risultati: le posizioni possono non essere esatte.' : ''}
            </p>
            {data.remaining ? (
              <RemainingInfo
                homeTeam={row.home_team}
                awayTeam={row.away_team}
                home={data.remaining[String(data.home_team_id)]}
                away={data.remaining[String(data.away_team_id)]}
                className="text-[12px] text-slate-500"
              />
            ) : null}
            {selected !== null ? <RecentGamesBox team={teamName(selected)} kind={kind} games={games} /> : null}
          </>
        ) : null}
      </aside>
    </div>
  )
}

/** Le ultime 5 partite della squadra scelta, dalla piu' vecchia all'ultima, con PT e finale. */
function RecentGamesBox({ team, kind, games }: { team: string | null; kind: StandingsKind; games: TableGame[] }) {
  return (
    <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3">
      <p className="text-sm font-semibold text-slate-800">
        {team} · ultime {games.length || 5} {SCOPE_WORDS[kind]}
      </p>
      {games.length === 0 ? (
        <p className="mt-1 text-[13px] text-slate-500">Nessuna partita finora.</p>
      ) : (
        <div className="mt-2 space-y-1.5">
          {games.map((g, i) => (
            <div key={i} className="grid grid-cols-[52px_minmax(0,1fr)_auto] items-center gap-2 text-[13px]">
              <span className="tabular-nums text-slate-500">
                {g.date ? new Date(`${g.date}T12:00:00Z`).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }) : '—'}
              </span>
              <span className="min-w-0 truncate text-slate-800">
                <span className="text-slate-500">{g.home ? 'in casa con' : 'fuori con'}</span> <b>{g.opponent ?? '?'}</b>
                {g.opponent_rank ? <span className="ml-1 text-[12px] text-slate-500">{g.opponent_rank}ª</span> : null}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="text-[11px] font-semibold text-slate-400">PT</span>
                <span className={`inline-flex h-6 min-w-[2.25rem] items-center justify-center rounded px-1 text-[12px] font-semibold tabular-nums ${g.ht_outcome ? SQUARE[g.ht_outcome] : 'bg-slate-50 text-slate-300'}`}>
                  {g.ht ?? '·'}
                </span>
                <span className="text-[11px] font-semibold text-slate-400">FT</span>
                <span className={`inline-flex h-6 min-w-[2.25rem] items-center justify-center rounded px-1 text-[12px] font-semibold tabular-nums ${g.ft_outcome ? SQUARE[g.ft_outcome] : 'bg-slate-50 text-slate-300'}`}>
                  {g.ft ?? '·'}
                </span>
              </span>
            </div>
          ))}
        </div>
      )}
      <p className="mt-2 text-[12px] text-slate-500">Posizione dell&apos;avversaria nella classifica totale.</p>
    </div>
  )
}

/** Scheda della partita (capitolato di Giovanni del 24/11/2026), dall'alto: testata con «Salva giocata», tipo partita,
 *  equilibrio e avvisi; cinque riquadri; «Segni · decidi qui»; forma con la striscia delle medie; contesto chiuso; note. */
function MatchDetail({
  row,
  canWrite,
  onKpi,
  onStandings,
  onClose,
  onNoteSaved,
}: {
  row: MatchTableRow
  canWrite: boolean
  onKpi: () => void
  onStandings: () => void
  onClose?: () => void
  onNoteSaved: (id: number, note: string) => void
}) {
  const [picked, setPicked] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const sign = row.evaluation?.signs.find((s) => s.key === picked) ?? null
  const disabled = row.started
    ? 'La partita è iniziata'
    : row.editable === false
      ? `${row.not_editable_reason ?? 'Meno di 3 gare in stagione'}: non si aggiunge al diario`
      : !canWrite
        ? 'Serve un account per salvare'
        : null
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] text-slate-500">
            {kickoffTime(row.kickoff)} · {row.country} · {row.league}
          </p>
          <h2 className="text-lg font-semibold text-slate-900">
            {row.home_team}
            {row.home_rank ? <span className="ml-1 text-[13px] font-normal text-slate-400">{row.home_rank}ª</span> : null}
            <span className="mx-1.5 text-slate-300">–</span>
            {row.away_team}
            {row.away_rank ? <span className="ml-1 text-[13px] font-normal text-slate-400">{row.away_rank}ª</span> : null}
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={btn} onClick={onStandings}>
            Classifica
          </button>
          <button type="button" className={btn} onClick={onKpi}>
            Pannello KPI
          </button>
          <SaveButton sign={sign} disabledReason={disabled} onClick={() => setSaving(true)} />
          {onClose ? (
            <button type="button" className={btn} onClick={onClose}>
              Chiudi
            </button>
          ) : null}
        </div>
      </div>
      <div className="-mt-2">
        <HeaderTypeLine row={row} />
        <HeaderAlerts row={row} />
        {disabled && !row.started ? <p className="mt-1 text-[12px] text-amber-700">{disabled}</p> : null}
        {!row.standings_complete ? (
          <p className="mt-1 text-[12px] text-amber-700" title="Nel campionato mancano alcuni risultati: posizioni e livelli possono non essere esatti">
            classifica parziale
          </p>
        ) : null}
        <RemainingLine row={row} />
      </div>

      <FiveBoxes row={row} />
      <SignsTable evaluation={row.evaluation} selectedKey={picked} onPick={(k) => setPicked((p) => (p === k ? null : k))} />
      <FormBlock row={row} />
      <ContextSection row={row} legend={<FormNotes />} />
      <NoteEditor key={row.today_fixture_id} row={row} canWrite={canWrite} onSaved={onNoteSaved} />

      {saving && sign ? <JournalDialog todayFixtureId={row.today_fixture_id} source="tabella" marketKey={sign.key} onClose={() => setSaving(false)} /> : null}
    </div>
  )
}

export function MatchTable() {
  const today = romeDate(0)
  const tomorrow = romeDate(1)
  const [day, setDay] = useState(today)
  const [upcoming, setUpcoming] = useState(true)
  const [country, setCountry] = useState('')
  const [league, setLeague] = useState('')
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [order, setOrder] = useState<Order>('time')
  const [playable, setPlayable] = useState(false)
  const [matchType, setMatchType] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<MatchTableResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [kpiRow, setKpiRow] = useState<MatchTableRow | null>(null)
  const [standingsRow, setStandingsRow] = useState<MatchTableRow | null>(null)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const wide = useIsWide()

  const load = useCallback(
    () =>
      getMatchTable({
        day,
        upcoming,
        country: country || undefined,
        league: league || undefined,
        q: search || undefined,
        page,
        playable,
        match_type: matchType || undefined,
      }).then(
        (r) => {
          setData(r)
          setError(null)
          setLoading(false)
        },
        (e: unknown) => {
          setError(errorText(e))
          setLoading(false)
        },
      ),
    [day, upcoming, country, league, search, page, playable, matchType],
  )
  useEffect(() => {
    void load()
  }, [load])

  // la ricerca parte poco dopo aver smesso di scrivere
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(query.trim())
      setPage(1)
    }, 400)
    return () => clearTimeout(t)
  }, [query])

  const rows = useMemo(() => data?.rows ?? [], [data])
  const selected = rows.find((r) => r.today_fixture_id === selectedId) ?? rows[0] ?? null
  const groups = useMemo(() => {
    if (order === 'time') return [{ key: '', label: '', rows }]
    const map = new Map<string, MatchTableRow[]>()
    for (const r of rows) {
      const key = `${r.country ?? ''} · ${r.league ?? ''}`
      map.set(key, [...(map.get(key) ?? []), r])
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, rs]) => ({ key, label: key, rows: rs }))
  }, [rows, order])

  const onNoteSaved = useCallback((id: number, note: string) => {
    setData((d) => (d ? { ...d, rows: d.rows.map((r) => (r.today_fixture_id === id ? { ...r, my_note: note } : r)) } : d))
  }, [])

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  const resetTo = (next: () => void) => {
    next()
    setPage(1)
    setSelectedId(null)
  }

  return (
    <div className="space-y-4">
      <div className={`${todayCard} ${todayCardPadding} space-y-3`}>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex overflow-hidden rounded-lg border border-slate-200" role="group" aria-label="Giorno">
            {[
              [today, 'Oggi'],
              [tomorrow, 'Domani'],
            ].map(([d, label]) => (
              <button
                key={d}
                type="button"
                onClick={() => resetTo(() => setDay(d))}
                className={`px-3 py-2 text-sm font-medium ${day === d ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 hover:bg-slate-50'}`}
              >
                {label}
              </button>
            ))}
          </div>
          <input
            type="date"
            className={selectClass}
            value={day}
            onChange={(e) => resetTo(() => setDay(e.target.value || today))}
            aria-label="Giorno"
          />
          <select className={selectClass} value={country} onChange={(e) => resetTo(() => { setCountry(e.target.value); setLeague('') })} aria-label="Nazione">
            <option value="">Tutte le nazioni</option>
            {(data?.countries ?? []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select className={selectClass} value={league} onChange={(e) => resetTo(() => setLeague(e.target.value))} aria-label="Campionato">
            <option value="">Tutti i campionati</option>
            {(data?.leagues ?? []).map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
          <input className={`${selectClass} min-w-[180px] flex-1`} placeholder="Cerca squadra" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Cerca squadra" />
          <select className={selectClass} value={order} onChange={(e) => setOrder(e.target.value as Order)} aria-label="Ordine">
            <option value="time">Per orario</option>
            <option value="league">Per campionato</option>
          </select>
          <button
            type='button'
            aria-pressed={playable}
            onClick={() => resetTo(() => setPlayable((v) => !v))}
            className={`rounded-lg border px-3 py-2 text-sm font-medium ${playable ? 'border-[#2457B3] bg-[#E3EDFF] text-[#2457B3]' : 'border-slate-300 bg-white text-slate-700'}`}
          >
            Solo con segni giocabili
          </button>
          <select className={selectClass} value={matchType} onChange={(e) => resetTo(() => setMatchType(e.target.value))} aria-label='Tipo partita'>
            <option value=''>Tutti i tipi partita</option>
            {(data?.match_types ?? []).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <label className='flex items-center gap-2 text-sm text-slate-700'>
            <input type='checkbox' checked={upcoming} onChange={(e) => resetTo(() => setUpcoming(e.target.checked))} />
            Solo da giocare
          </label>
          <span className='text-[13px]' style={{ color: C.cmd.text }}>
            quote delle {data?.odds_at ? kickoffTime(data.odds_at) : 'n.d.'}
          </span>
        </div>
        <p className="text-[13px] text-slate-500">
          <span className="capitalize">{dayLabel(day)}</span>
          {data ? ` · ${data.total} partite${upcoming ? ' da giocare' : ''} su ${data.total_day}` : ''}
          {pages > 1 ? ` · pagina ${page} di ${pages}` : ''}. Pallino = affidabilità dei dati · icona = meteo al via · etichetta = tipo partita dalle
          quote Bet365, numero = indice di equilibrio Cecchino (0-100) · ✓ segni giocabili o da verificare, ✕ bloccati. Le cifre ±forza si leggono nella
          scheda. Solo le partite calcolate da Cecchino.
        </p>
      </div>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {loading && !data ? <p className="text-sm text-slate-500">Preparo la tabella…</p> : null}

      {data && rows.length === 0 ? (
        <div className={`${todayCard} ${todayCardPadding} text-sm text-slate-600`}>
          {data.total_day === 0 && day > today
            ? 'Le partite di domani arrivano con la scansione delle 6 di ogni mattina.'
            : `Nessuna partita con almeno 3 gare recenti ${upcoming ? 'ancora da giocare ' : ''}per questi filtri.`}
        </div>
      ) : null}

      {data && rows.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
          <div className="space-y-3">
            <div className={`${todayCard} overflow-hidden`}>
              <div className="hidden grid-cols-[48px_minmax(0,1fr)_auto_64px_110px] gap-x-3 border-b border-slate-200 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400 sm:grid">
                <span>Ora</span>
                <span>Partita</span>
                <span>Forma casa · fuori</span>
                <span>Segni</span>
                <span className="text-right">1 · X · 2</span>
              </div>
              {groups.map((g) => (
                <div key={g.key || 'all'}>
                  {g.label ? (
                    <button
                      type="button"
                      onClick={() => setCollapsed((c) => ({ ...c, [g.key]: !c[g.key] }))}
                      className="flex w-full items-center justify-between border-b border-slate-100 bg-slate-50 px-3 py-1.5 text-left text-[12px] font-semibold text-slate-600"
                    >
                      <span>{g.label}</span>
                      <span className="text-slate-400">
                        {g.rows.length} {collapsed[g.key] ? '▸' : '▾'}
                      </span>
                    </button>
                  ) : null}
                  {collapsed[g.key]
                    ? null
                    : g.rows.map((r) => (
                        <ListRow
                          key={`${r.today_fixture_id}-${data.day}`}
                          row={r}
                          showLeague={order === 'time'}
                          selected={selected?.today_fixture_id === r.today_fixture_id}
                          onSelect={() => {
                            setSelectedId(r.today_fixture_id)
                            setDrawerOpen(true)
                          }}
                        />
                      ))}
                </div>
              ))}
            </div>
            {pages > 1 ? (
              <div className="flex items-center gap-2">
                <button type="button" className={btn} disabled={page <= 1} onClick={() => { setPage((p) => Math.max(1, p - 1)); setSelectedId(null) }}>
                  ‹ Precedenti
                </button>
                <span className="text-[13px] text-slate-600">
                  {page} / {pages}
                </span>
                <button type="button" className={btn} disabled={page >= pages} onClick={() => { setPage((p) => Math.min(pages, p + 1)); setSelectedId(null) }}>
                  Successive ›
                </button>
              </div>
            ) : null}
          </div>

          {selected && wide ? (
            <aside className={`${todayCard} ${todayCardPadding} self-start xl:sticky xl:top-4`}>
              <MatchDetail
                key={selected.today_fixture_id}
                row={selected}
                canWrite={data.can_write}
                onKpi={() => setKpiRow(selected)}
                onStandings={() => setStandingsRow(selected)}
                onNoteSaved={onNoteSaved}
              />
            </aside>
          ) : null}
        </div>
      ) : null}

      {selected && drawerOpen && !wide && data ? (
        <div className="fixed inset-0 z-[65] flex justify-end bg-slate-900/40" role="dialog" aria-modal="true" onClick={() => setDrawerOpen(false)}>
          <aside className="h-full w-full max-w-xl overflow-y-auto bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <MatchDetail
              key={`m-${selected.today_fixture_id}`}
              row={selected}
              canWrite={data.can_write}
              onKpi={() => setKpiRow(selected)}
              onStandings={() => setStandingsRow(selected)}
              onClose={() => setDrawerOpen(false)}
              onNoteSaved={onNoteSaved}
            />
          </aside>
        </div>
      ) : null}

      {kpiRow ? <KpiDrawer row={kpiRow} onClose={() => setKpiRow(null)} /> : null}
      {standingsRow ? <StandingsDrawer row={standingsRow} onClose={() => setStandingsRow(null)} /> : null}
    </div>
  )
}
