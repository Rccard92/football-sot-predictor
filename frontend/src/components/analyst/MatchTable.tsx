import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { AdminHttpError } from '../../lib/api'
import {
  getMatchTable,
  saveMatchNote,
  type MatchTableResponse,
  type MatchTableRow,
  type TableBlock,
  type TableBlockKey,
  type TableCards,
  type TableGame,
  type TableOutcome,
} from '../../lib/analystJournalApi'
import { getCecchinoTodayDetail, type CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { CecchinoTodayKpiPanel } from '../cecchino/CecchinoTodayKpiPanel'
import { todayCard, todayCardPadding } from '../cecchino/cecchinoTodayStyles'
import { AddToJournalButton } from './AddToJournalButton'

/** Tabella analisi (bozza di Giovanni, 05/11/2026): una riga per partita con forma, gol, gialli, equilibrio e
 *  quote; da qui Cristian apre il pannello KPI, aggiunge la partita al diario e scrive le sue note. */

const btn = 'rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[13px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60'
const selectClass = 'rounded-lg border border-slate-300 px-3 py-2 text-sm'
const TH = 'border-b border-slate-200 px-2 py-2 text-left align-bottom text-[12px] font-semibold uppercase tracking-wide text-slate-500'
const TD = 'border-b border-slate-100 px-2 py-2 align-top text-[13px]'
const OUTCOME_CLASS: Record<TableOutcome, string> = {
  V: 'text-emerald-700',
  P: 'text-rose-700',
  N: 'text-slate-400',
}
const OUTCOME_WORD: Record<TableOutcome, string> = { V: 'vinta', N: 'pareggiata', P: 'persa' }
const FORM_COLUMNS: { key: TableBlockKey; label: string }[] = [
  { key: 'forma_casa', label: 'Forma casa' },
  { key: 'forma_fuori', label: 'Forma fuori' },
  { key: 'forma_totale_casa', label: 'Forma totale casa' },
  { key: 'forma_totale_fuori', label: 'Forma totale fuori' },
]
const MAIN_QUOTES = ['HOME', 'DRAW', 'AWAY']

function romeToday(): string {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Rome' })
}

function kickoffTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' })
}

function errorText(e: unknown): string {
  return e instanceof AdminHttpError ? e.message : e instanceof Error ? e.message : 'Errore'
}

function gameTitle(g: TableGame, half: 'PT' | 'FT'): string {
  const outcome = half === 'PT' ? g.ht_outcome : g.ft_outcome
  const score = half === 'PT' ? g.ht : g.ft
  const rank = g.opponent_rank ? ` (${g.opponent_rank}ª in classifica)` : ''
  const date = g.date ? new Date(`${g.date}T12:00:00Z`).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }) : ''
  return `${date} ${g.home ? 'in casa contro' : 'fuori contro'} ${g.opponent ?? '?'}${rank}: ${score ?? '—'} ${half}${outcome ? `, ${OUTCOME_WORD[outcome]}` : ''}`
}

/** Una riga di risultati: verde vinta, rossa persa, grigia pareggiata; grassetto contro chi sta piu' in alto. */
function ResultsLine({ label, games, half }: { label: string; games: TableGame[]; half: 'PT' | 'FT' }) {
  return (
    <div className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="w-5 text-[11px] font-semibold text-slate-400">{label}</span>
      {games.map((g, i) => {
        const outcome = half === 'PT' ? g.ht_outcome : g.ft_outcome
        const score = half === 'PT' ? g.ht : g.ft
        const bold = half === 'PT' ? g.bold_ht : g.bold_ft
        return (
          <span
            key={i}
            title={gameTitle(g, half)}
            className={`tabular-nums ${outcome ? OUTCOME_CLASS[outcome] : 'text-slate-300'} ${bold ? 'font-bold' : ''}`}
          >
            {score ?? '—'}
          </span>
        )
      })}
    </div>
  )
}

function Insufficient({ games }: { games: number }) {
  return (
    <span className="text-slate-400" title={`Solo ${games} gare: ne servono almeno 3`}>
      —
    </span>
  )
}

function FormCell({ block }: { block: TableBlock }) {
  if (!block.enough) return <Insufficient games={block.games} />
  return (
    <div className="space-y-0.5">
      <p className="font-semibold text-slate-900">
        {block.points} pt <span className="text-[12px] font-normal text-slate-400">· {block.games} gare</span>
      </p>
      <ResultsLine label="PT" games={block.results} half="PT" />
      <ResultsLine label="FT" games={block.results} half="FT" />
    </div>
  )
}

function GoalsCell({ block }: { block: TableBlock }) {
  if (!block.enough) return <Insufficient games={block.games} />
  return (
    <div className="space-y-0.5">
      <p className="font-semibold tabular-nums text-slate-900" title="Gol fatti contro subiti">
        {block.scored} <span className="font-normal text-slate-400">vs</span> {block.conceded}
      </p>
      <ResultsLine label="PT" games={block.results} half="PT" />
      <ResultsLine label="FT" games={block.results} half="FT" />
    </div>
  )
}

function CardsCell({ cards }: { cards: TableCards }) {
  if (!cards.available) {
    return (
      <span className="text-slate-400" title="Statistiche dei cartellini non disponibili per queste gare">
        n.d.
      </span>
    )
  }
  return (
    <div className="space-y-0.5 tabular-nums">
      <p>
        <span className="text-[12px] text-slate-400">Fatti</span> <span className="font-semibold text-slate-900">{cards.own}</span>
      </p>
      <p>
        <span className="text-[12px] text-slate-400">Subiti</span> <span className="font-semibold text-slate-900">{cards.opponents}</span>
      </p>
      {cards.games < 5 ? <p className="text-[11px] text-slate-400">su {cards.games} gare</p> : null}
    </div>
  )
}

function BalanceCell({ row }: { row: MatchTableRow }) {
  if (!row.balance) return <span className="text-slate-400">—</span>
  return (
    <div>
      <p className="font-semibold tabular-nums text-slate-900">{row.balance.index ?? '—'}</p>
      <p className="text-[12px] text-slate-600">{row.balance.class ?? ''}</p>
    </div>
  )
}

function quoteText(q: number | null | undefined): string {
  return q == null ? '—' : q.toFixed(2).replace('.', ',')
}

/** Nota dell'analista: si salva da sola poco dopo aver smesso di scrivere. */
function NoteCell({ row, canWrite }: { row: MatchTableRow; canWrite: boolean }) {
  const [text, setText] = useState(row.my_note)
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const last = useRef(row.my_note)

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
  }, [])

  const save = (value: string) => {
    if (value === last.current) return
    setState('saving')
    saveMatchNote(row.today_fixture_id, value).then(
      () => {
        last.current = value
        setState('saved')
      },
      () => setState('error'),
    )
  }

  return (
    <div className="space-y-1">
      <textarea
        className="h-20 w-full min-w-[260px] resize-y rounded-lg border border-slate-200 px-2.5 py-1.5 text-[13px] focus:border-slate-400 focus:outline-none disabled:bg-slate-50"
        placeholder={canWrite ? 'Note analista' : 'Serve un account per scrivere'}
        value={text}
        disabled={!canWrite}
        onChange={(e) => {
          const value = e.target.value
          setText(value)
          setState('idle')
          if (timer.current) clearTimeout(timer.current)
          timer.current = setTimeout(() => save(value), 800)
        }}
        onBlur={() => {
          if (timer.current) clearTimeout(timer.current)
          save(text)
        }}
      />
      <p className="h-4 text-[11px] text-slate-400">
        {state === 'saving' ? 'Salvo…' : state === 'saved' ? 'Salvata' : state === 'error' ? <span className="text-rose-600">Non salvata, riprova</span> : ''}
      </p>
      {row.other_notes.map((n, i) => (
        <p key={i} className="rounded-md bg-slate-50 px-2 py-1 text-[12px] text-slate-600">
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
    <div className="fixed inset-0 z-[65] flex justify-end bg-slate-900/40" role="dialog" aria-modal="true" onClick={onClose}>
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

function TableRow({ row, canWrite, onKpi }: { row: MatchTableRow; canWrite: boolean; onKpi: (row: MatchTableRow) => void }) {
  const [showQuotes, setShowQuotes] = useState(false)
  const main = MAIN_QUOTES.map((k) => row.quotes.find((q) => q.key === k))
  const others = row.quotes.filter((q) => !MAIN_QUOTES.includes(q.key))
  const groups = [...new Set(others.map((q) => q.group))]
  return (
    <Fragment>
      <tr className={row.started ? 'bg-slate-50/70 text-slate-500' : ''}>
        <td className={`${TD} sticky left-0 z-[1] whitespace-nowrap bg-white`}>
          <p className="font-semibold tabular-nums text-slate-900">{kickoffTime(row.kickoff)}</p>
          {row.started ? <p className="text-[11px] text-slate-400">iniziata</p> : null}
        </td>
        <td className={`${TD} min-w-[210px]`}>
          <p className="text-[12px] text-slate-500">
            {row.country} · {row.league}
          </p>
          <p className="font-semibold text-slate-900">
            {row.home_team}
            {row.home_rank ? <span className="ml-1 text-[12px] font-normal text-slate-400">{row.home_rank}ª</span> : null}
          </p>
          <p className="font-semibold text-slate-900">
            {row.away_team}
            {row.away_rank ? <span className="ml-1 text-[12px] font-normal text-slate-400">{row.away_rank}ª</span> : null}
          </p>
          {!row.standings_complete ? (
            <p className="text-[11px] text-amber-700" title="Nel campionato mancano alcuni risultati: posizioni e grassetti possono non essere esatti">
              classifica parziale
            </p>
          ) : null}
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <button type="button" className={btn} onClick={() => onKpi(row)}>
              Pannello KPI
            </button>
            {!row.started ? <AddToJournalButton todayFixtureId={row.today_fixture_id} source="tabella" compact /> : null}
          </div>
        </td>
        <td className={TD}>
          <BalanceCell row={row} />
        </td>
        {FORM_COLUMNS.map((c) => (
          <td key={c.key} className={TD}>
            <FormCell block={row.blocks[c.key]} />
          </td>
        ))}
        <td className={TD}>
          <GoalsCell block={row.blocks.forma_casa} />
        </td>
        <td className={TD}>
          <GoalsCell block={row.blocks.forma_fuori} />
        </td>
        <td className={TD}>
          <CardsCell cards={row.yellows.home} />
        </td>
        <td className={TD}>
          <CardsCell cards={row.yellows.away} />
        </td>
        <td className={`${TD} whitespace-nowrap`}>
          <div className="grid grid-cols-3 gap-x-2 tabular-nums">
            {['1', 'X', '2'].map((l) => (
              <span key={l} className="text-center text-[11px] font-semibold text-slate-400">
                {l}
              </span>
            ))}
            {main.map((q, i) => (
              <span key={i} className="text-center font-semibold text-slate-900">
                {quoteText(q?.quota)}
              </span>
            ))}
          </div>
          {others.length ? (
            <button type="button" className="mt-1 text-[12px] font-medium text-indigo-700 hover:underline" onClick={() => setShowQuotes((v) => !v)}>
              {showQuotes ? 'Nascondi quote' : `Altre ${others.length} quote`}
            </button>
          ) : null}
        </td>
        <td className={TD}>
          <NoteCell row={row} canWrite={canWrite} />
        </td>
      </tr>
      {showQuotes ? (
        <tr>
          <td className="border-b border-slate-100 bg-slate-50/60 px-2 py-2" colSpan={14}>
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-[13px]">
              {groups.map((g) => (
                <div key={g}>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{g}</p>
                  <div className="mt-0.5 flex flex-wrap gap-x-3">
                    {others
                      .filter((q) => q.group === g)
                      .map((q) => (
                        <span key={q.key} className="whitespace-nowrap">
                          <span className="text-slate-500">{q.label}</span> <b className="tabular-nums text-slate-900">{quoteText(q.quota)}</b>
                        </span>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </td>
        </tr>
      ) : null}
    </Fragment>
  )
}

export function MatchTable() {
  const [day, setDay] = useState(romeToday)
  const [upcoming, setUpcoming] = useState(true)
  const [country, setCountry] = useState('')
  const [league, setLeague] = useState('')
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<MatchTableResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [kpiRow, setKpiRow] = useState<MatchTableRow | null>(null)

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

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="space-y-4">
      <div className={`${todayCard} ${todayCardPadding} space-y-3`}>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[13px] text-slate-600">
            Giorno
            <input
              type="date"
              className={`${selectClass} mt-1 block`}
              value={day}
              onChange={(e) => {
                setDay(e.target.value || romeToday())
                setPage(1)
              }}
            />
          </label>
          <select
            className={selectClass}
            value={country}
            onChange={(e) => {
              setCountry(e.target.value)
              setLeague('')
              setPage(1)
            }}
            aria-label="Nazione"
          >
            <option value="">Tutte le nazioni</option>
            {(data?.countries ?? []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            className={selectClass}
            value={league}
            onChange={(e) => {
              setLeague(e.target.value)
              setPage(1)
            }}
            aria-label="Campionato"
          >
            <option value="">Tutti i campionati</option>
            {(data?.leagues ?? []).map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
          <input className={`${selectClass} min-w-[200px]`} placeholder="Cerca squadra" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Cerca squadra" />
          <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={upcoming}
              onChange={(e) => {
                setUpcoming(e.target.checked)
                setPage(1)
              }}
            />
            Solo da giocare
          </label>
        </div>
        <p className="text-[13px] text-slate-500">
          Risultati dal punto di vista di ogni squadra (fatti-subiti), dalla gara più vecchia a sinistra all&apos;ultima a destra:{' '}
          <span className="font-semibold text-emerald-700">vinta</span>, <span className="font-semibold text-rose-700">persa</span>,{' '}
          <span className="text-slate-400">pareggiata</span>; in <b>grassetto</b> contro una squadra più in alto in classifica. Punti 3/1/0 sul risultato
          finale, da 3 a 5 gare dello stesso campionato. Gialli solo dove ci sono le statistiche (n.d. altrove). Passa sopra un risultato per vedere
          avversaria e data.
        </p>
      </div>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {loading && !data ? <p className="text-sm text-slate-500">Preparo la tabella…</p> : null}

      {data ? (
        <>
          <p className="text-[13px] text-slate-500">
            {data.total} partite{upcoming ? ' da giocare' : ''} su {data.total_day} del giorno
            {pages > 1 ? ` · pagina ${data.page} di ${pages}` : ''}
          </p>
          {data.rows.length === 0 ? (
            <div className={`${todayCard} ${todayCardPadding} text-sm text-slate-600`}>
              Nessuna partita con almeno 3 gare recenti {upcoming ? 'ancora da giocare ' : ''}per questi filtri.
            </div>
          ) : (
            <div className={`${todayCard} overflow-x-auto`}>
              <table className="min-w-full border-separate border-spacing-0">
                <thead>
                  <tr>
                    <th className={`${TH} sticky left-0 z-[1] bg-white`}>Ora</th>
                    <th className={TH}>Incontro</th>
                    <th className={TH}>Equilibrio vs squilibrio</th>
                    {FORM_COLUMNS.map((c) => (
                      <th key={c.key} className={TH}>
                        {c.label}
                      </th>
                    ))}
                    <th className={TH}>Goal casa solo in casa</th>
                    <th className={TH}>Goal fuori solo fuori</th>
                    <th className={TH}>Gialli casa ultime 5</th>
                    <th className={TH}>Gialli fuori ultime 5</th>
                    <th className={TH}>Quote</th>
                    <th className={`${TH} min-w-[280px]`}>Note analista</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => (
                    <TableRow key={`${r.today_fixture_id}-${data.day}`} row={r} canWrite={data.can_write} onKpi={setKpiRow} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {pages > 1 ? (
            <div className="flex items-center gap-2">
              <button type="button" className={btn} disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                ‹ Precedenti
              </button>
              <span className="text-[13px] text-slate-600">
                {page} / {pages}
              </span>
              <button type="button" className={btn} disabled={page >= pages} onClick={() => setPage((p) => Math.min(pages, p + 1))}>
                Successive ›
              </button>
            </div>
          ) : null}
        </>
      ) : null}

      {kpiRow ? <KpiDrawer row={kpiRow} onClose={() => setKpiRow(null)} /> : null}
    </div>
  )
}
