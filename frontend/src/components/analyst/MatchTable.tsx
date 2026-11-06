import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AdminHttpError } from '../../lib/api'
import {
  getMatchStandings,
  getMatchTable,
  saveMatchNote,
  type MatchStandings,
  type MatchTableResponse,
  type MatchTableRow,
  type StandingsKind,
  type TableBlock,
  type TableCards,
  type TableGame,
  type TableOutcome,
} from '../../lib/analystJournalApi'
import { getCecchinoTodayDetail, type CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { CecchinoTodayKpiPanel } from '../cecchino/CecchinoTodayKpiPanel'
import { todayCard, todayCardPadding } from '../cecchino/cecchinoTodayStyles'
import { AddToJournalButton } from './AddToJournalButton'

/** Tabella analisi (bozza di Giovanni, 05/11/2026; grafica rifatta il 05/11): lista compatta delle partite con
 *  la forma a quadratini, e scheda della partita scelta con il dettaglio, il pannello KPI, il diario e le note.
 *  Il giro del mattino scansiona anche domani, quindi qui si preparano oggi le partite di domani.
 *  06/11 (richieste di Giovanni): risultato dentro il quadratino, cornice anche sui pareggi, gol PT e FT in ogni
 *  blocco, media dei gialli, classifica completa (totale, casa, trasferta), indicatore di equilibrio tolto. */

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

function decimal(v: number): string {
  return v.toLocaleString('it-IT', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}

function gameTitle(g: TableGame, half: 'PT' | 'FT'): string {
  const outcome = half === 'PT' ? g.ht_outcome : g.ft_outcome
  const score = half === 'PT' ? g.ht : g.ft
  const rank = g.opponent_rank ? ` (${g.opponent_rank}ª)` : ''
  const date = g.date ? new Date(`${g.date}T12:00:00Z`).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }) : ''
  return `${date} ${g.home ? 'in casa con' : 'fuori con'} ${g.opponent ?? '?'}${rank}: ${score ?? '—'} ${half}${outcome ? `, ${OUTCOME_WORD[outcome]}` : ''}`
}

/** Quadratini con il risultato (gol della squadra prima), dalla gara piu' vecchia (sinistra) all'ultima (destra):
 *  verde vinta, grigio pari, rosso persa; cornice = avversaria piu' in alto in classifica. */
function FormSquares({ games, half, size = 'sm' }: { games: TableGame[]; half: 'PT' | 'FT'; size?: 'sm' | 'md' }) {
  const box = size === 'md' ? 'h-6 min-w-[2.25rem] px-1 text-[12px]' : 'h-5 min-w-[2rem] px-0.5 text-[11px]'
  return (
    <span className="inline-flex gap-0.5 align-middle">
      {games.map((g, i) => {
        const outcome = half === 'PT' ? g.ht_outcome : g.ft_outcome
        const score = half === 'PT' ? g.ht : g.ft
        const strong = half === 'PT' ? g.bold_ht : g.bold_ft
        return (
          <span
            key={i}
            title={gameTitle(g, half)}
            className={`inline-flex ${box} items-center justify-center rounded font-semibold tabular-nums ${outcome ? SQUARE[outcome] : 'bg-slate-50 text-slate-300'} ${
              strong ? 'ring-2 ring-inset ring-current' : ''
            }`}
          >
            {outcome && score ? score : '·'}
          </span>
        )
      })}
    </span>
  )
}

function ListForm({ block }: { block: TableBlock }) {
  if (!block.enough) return <span className="text-[12px] text-slate-400" title={`Solo ${block.games} gare`}>—</span>
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <FormSquares games={block.results} half="FT" />
      <span className="w-6 text-[13px] font-semibold tabular-nums text-slate-900">{block.points}</span>
    </span>
  )
}

function ListRow({ row, selected, onSelect, showLeague }: { row: MatchTableRow; selected: boolean; onSelect: () => void; showLeague: boolean }) {
  const main = MAIN_QUOTES.map((k) => row.quotes.find((q) => q.key === k)?.quota)
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`grid w-full grid-cols-[44px_minmax(0,1fr)] gap-x-3 gap-y-1.5 border-b border-slate-100 px-3 py-2.5 text-left text-[13px] transition sm:grid-cols-[44px_minmax(0,1fr)_auto_96px] ${
        selected ? 'bg-indigo-50/70' : 'hover:bg-slate-50'
      } ${row.started ? 'opacity-70' : ''}`}
      aria-pressed={selected}
    >
      <span className="pt-0.5 font-semibold tabular-nums text-slate-900">{kickoffTime(row.kickoff)}</span>
      <span className="min-w-0">
        <span className="block truncate font-medium text-slate-900">
          {row.home_team}
          {row.home_rank ? <span className="ml-1 text-[12px] font-normal text-slate-400">{row.home_rank}ª</span> : null}
          <span className="mx-1 text-slate-300">–</span>
          {row.away_team}
          {row.away_rank ? <span className="ml-1 text-[12px] font-normal text-slate-400">{row.away_rank}ª</span> : null}
        </span>
        <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
          {showLeague ? <span className="truncate text-[12px] text-slate-500">{row.league}</span> : null}
          {row.my_note.trim() ? <span className="text-[12px] text-indigo-700" title="Hai scritto una nota">● nota</span> : null}
          {row.started ? <span className="text-[12px] text-slate-400">iniziata</span> : null}
        </span>
      </span>
      <span className="col-start-2 flex flex-col gap-1 sm:col-start-auto">
        <span className="flex items-center gap-1.5">
          <span className="w-8 text-[11px] text-slate-400">casa</span>
          <ListForm block={row.blocks.forma_casa} />
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-8 text-[11px] text-slate-400">fuori</span>
          <ListForm block={row.blocks.forma_fuori} />
        </span>
      </span>
      <span className="col-start-2 grid grid-cols-3 gap-x-1 text-center tabular-nums sm:col-start-auto">
        {['1', 'X', '2'].map((l) => (
          <span key={l} className="text-[11px] text-slate-400">
            {l}
          </span>
        ))}
        {main.map((q, i) => (
          <span key={i} className="font-semibold text-slate-900">
            {quoteText(q)}
          </span>
        ))}
      </span>
    </button>
  )
}

function GoalsLine({ label, scored, conceded, games, total }: { label: string; scored: number; conceded: number; games: number; total: number }) {
  return (
    <p className="text-[13px] text-slate-700">
      <span className="inline-block w-14 text-[12px] text-slate-500">Gol {label}</span>
      <b className="tabular-nums">{scored}</b> fatti · <b className="tabular-nums">{conceded}</b> subiti
      {games < total ? <span className="text-[12px] text-slate-400"> (su {games})</span> : null}
    </p>
  )
}

function BlockCard({ title, block }: { title: string; block: TableBlock }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <p className={LABEL}>{title}</p>
      {!block.enough ? (
        <p className="mt-1 text-[13px] text-slate-400">Meno di 3 gare ({block.games})</p>
      ) : (
        <>
          <p className="mt-0.5 text-[15px] font-semibold text-slate-900">
            {block.points} pt <span className="text-[12px] font-normal text-slate-500">su {block.max_points} · {block.games} gare</span>
          </p>
          <div className="mt-1.5 space-y-1">
            <p className="flex items-center gap-2">
              <span className="w-5 text-[11px] font-semibold text-slate-400">PT</span>
              <FormSquares games={block.results} half="PT" size="md" />
            </p>
            <p className="flex items-center gap-2">
              <span className="w-5 text-[11px] font-semibold text-slate-400">FT</span>
              <FormSquares games={block.results} half="FT" size="md" />
            </p>
          </div>
          <div className="mt-1.5 space-y-0.5">
            <GoalsLine label="PT" scored={block.ht_scored ?? 0} conceded={block.ht_conceded ?? 0} games={block.ht_games ?? 0} total={block.games} />
            <GoalsLine label="FT" scored={block.scored} conceded={block.conceded} games={block.games} total={block.games} />
          </div>
        </>
      )}
    </div>
  )
}

function CardsLine({ label, cards }: { label: string; cards: TableCards }) {
  return (
    <p className="flex items-baseline justify-between gap-2 text-[13px]">
      <span className="text-slate-600">{label}</span>
      {cards.available ? (
        <span className="text-right tabular-nums">
          media <b className="text-slate-900">{decimal(cards.own_avg ?? cards.own / cards.games)}</b> fatti ·{' '}
          <b className="text-slate-900">{decimal(cards.opponents_avg ?? cards.opponents / cards.games)}</b> subiti
          <span className="block text-[12px] text-slate-400">
            totale {cards.own} · {cards.opponents} in {cards.games} gare
          </span>
        </span>
      ) : (
        <span className="text-slate-400" title="Statistiche dei cartellini non disponibili per queste gare">
          n.d.
        </span>
      )}
    </p>
  )
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

/** Classifica completa del campionato, ricostruita dai risultati: totale, solo casa, solo trasferta. */
function StandingsDrawer({ row, onClose }: { row: MatchTableRow; onClose: () => void }) {
  const [data, setData] = useState<MatchStandings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [kind, setKind] = useState<StandingsKind>('total')
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
  const mark = (id: number) => (data && (id === data.home_team_id || id === data.away_team_id) ? 'bg-indigo-50 font-semibold text-slate-900' : 'text-slate-700')
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
            <table className="w-full text-[13px] tabular-nums">
              <thead>
                <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-400">
                  <th className="py-1.5 pr-2 text-left font-semibold">#</th>
                  <th className="py-1.5 pr-2 text-left font-semibold">Squadra</th>
                  {['G', 'V', 'N', 'P', 'GF', 'GS', 'DR', 'Pt'].map((h) => (
                    <th key={h} className="px-1 py-1.5 text-right font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.team_id} className={`border-b border-slate-100 ${mark(r.team_id)}`}>
                    <td className="py-1.5 pr-2">{r.rank}</td>
                    <td className="py-1.5 pr-2">{r.team ?? '—'}</td>
                    <td className="px-1 py-1.5 text-right">{r.played}</td>
                    <td className="px-1 py-1.5 text-right">{r.won}</td>
                    <td className="px-1 py-1.5 text-right">{r.drawn}</td>
                    <td className="px-1 py-1.5 text-right">{r.lost}</td>
                    <td className="px-1 py-1.5 text-right">{r.gf}</td>
                    <td className="px-1 py-1.5 text-right">{r.ga}</td>
                    <td className="px-1 py-1.5 text-right">{r.gd > 0 ? `+${r.gd}` : r.gd}</td>
                    <td className="px-1 py-1.5 text-right font-semibold text-slate-900">{r.points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-[12px] text-slate-500">
              Ricostruita dai {data.games} risultati del campionato nel nostro archivio.
              {!data.complete ? ' Mancano alcuni risultati: le posizioni possono non essere esatte.' : ''}
            </p>
          </>
        ) : null}
      </aside>
    </div>
  )
}

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
  const others = row.quotes.filter((q) => !MAIN_QUOTES.includes(q.key))
  const groups = [...new Set(row.quotes.map((q) => q.group))]
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] text-slate-500">
            {kickoffTime(row.kickoff)} · {row.country} · {row.league}
          </p>
          <h2 className="text-base font-semibold text-slate-900">
            {row.home_team}
            {row.home_rank ? <span className="ml-1 text-[13px] font-normal text-slate-400">{row.home_rank}ª</span> : null}
            <span className="mx-1.5 text-slate-300">–</span>
            {row.away_team}
            {row.away_rank ? <span className="ml-1 text-[13px] font-normal text-slate-400">{row.away_rank}ª</span> : null}
          </h2>
          {!row.standings_complete ? (
            <p className="mt-1 text-[12px] text-amber-700" title="Nel campionato mancano alcuni risultati: posizioni e cornici possono non essere esatte">
              classifica parziale
            </p>
          ) : null}
        </div>
        {onClose ? (
          <button type="button" className={btn} onClick={onClose}>
            Chiudi
          </button>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={btn} onClick={onKpi}>
          Pannello KPI
        </button>
        <button type="button" className={btn} onClick={onStandings}>
          Classifica
        </button>
        {!row.started ? <AddToJournalButton todayFixtureId={row.today_fixture_id} source="tabella" compact /> : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <BlockCard title={`Forma casa · ${row.home_team} in casa`} block={row.blocks.forma_casa} />
        <BlockCard title={`Forma fuori · ${row.away_team} fuori`} block={row.blocks.forma_fuori} />
        <BlockCard title={`Forma totale · ${row.home_team}`} block={row.blocks.forma_totale_casa} />
        <BlockCard title={`Forma totale · ${row.away_team}`} block={row.blocks.forma_totale_fuori} />
      </div>
      <p className="text-[12px] text-slate-500">
        Risultati con i gol della squadra per primi, dalla gara più vecchia a sinistra all&apos;ultima a destra. Cornice = contro una squadra più in alto in
        classifica (anche nei pareggi). Passa sopra un quadratino per avversaria e data.
      </p>

      <div className="space-y-1 rounded-xl bg-slate-50 p-3">
        <p className={LABEL}>Gialli ultime 5 gare</p>
        <CardsLine label={row.home_team} cards={row.yellows.home} />
        <CardsLine label={row.away_team} cards={row.yellows.away} />
      </div>

      {row.quotes.length ? (
        <div className="rounded-xl bg-slate-50 p-3">
          <p className={LABEL}>Quote ({row.quotes.length})</p>
          <div className="mt-1 space-y-1.5">
            {groups.map((g) => (
              <div key={g} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[13px]">
                <span className="w-36 shrink-0 text-[12px] text-slate-400">{g}</span>
                {row.quotes
                  .filter((q) => q.group === g)
                  .map((q) => (
                    <span key={q.key} className="whitespace-nowrap">
                      <span className="text-slate-500">{q.label}</span> <b className="tabular-nums text-slate-900">{quoteText(q.quota)}</b>
                    </span>
                  ))}
              </div>
            ))}
          </div>
          {others.length === 0 ? <p className="mt-1 text-[12px] text-slate-400">Solo 1, X e 2 disponibili.</p> : null}
        </div>
      ) : null}

      <NoteEditor key={row.today_fixture_id} row={row} canWrite={canWrite} onSaved={onNoteSaved} />
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
      getMatchTable({ day, upcoming, country: country || undefined, league: league || undefined, q: search || undefined, page }).then(
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
    [day, upcoming, country, league, search, page],
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
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={upcoming} onChange={(e) => resetTo(() => setUpcoming(e.target.checked))} />
            Solo da giocare
          </label>
        </div>
        <p className="text-[13px] text-slate-500">
          <span className="capitalize">{dayLabel(day)}</span>
          {data ? ` · ${data.total} partite${upcoming ? ' da giocare' : ''} su ${data.total_day}` : ''}
          {pages > 1 ? ` · pagina ${page} di ${pages}` : ''}. Quadratini con il risultato finale:{' '}
          <span className="font-semibold text-emerald-700">verde</span> vinta, <span className="font-semibold text-slate-500">grigio</span> pari,{' '}
          <span className="font-semibold text-rose-700">rosso</span> persa, con i punti accanto.
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
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div className="space-y-3">
            <div className={`${todayCard} overflow-hidden`}>
              <div className="hidden grid-cols-[44px_minmax(0,1fr)_auto_96px] gap-x-3 border-b border-slate-200 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400 sm:grid">
                <span>Ora</span>
                <span>Partita</span>
                <span>Forma casa · fuori</span>
                <span className="text-center">1 · X · 2</span>
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
