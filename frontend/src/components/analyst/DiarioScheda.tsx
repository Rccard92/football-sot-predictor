import { useState, type ReactNode } from 'react'
import type {
  DiffLevel,
  EvaluatedSign,
  MatchTableRow,
  RowEvaluation,
  SignState,
  TableBlock,
  TableCards,
  TableGame,
  TableOutcome,
  TeamSchedule,
  TeamSquad,
} from '../../lib/analystJournalApi'
import {
  BALANCE_HELP,
  C,
  CLASS_STYLE,
  MATCH_TYPE_HELP,
  OUTCOME_FILL,
  balanceDisagree,
  calendarSummary,
  ddmm,
  dec1,
  hhmm,
  moveRows,
  moveSummary,
  pct0,
  q2,
  readTime,
  saveButtonFor,
  signLabel,
  signedPct,
  starters,
} from './diarioFormat'

/** Scheda della partita del Diario (capitolato di Giovanni del 24/11/2026, modifiche 1-17).
 *  Regole generali: nessun dato si toglie (si sposta, si unisce o si chiude), dato non noto = «n.d.» mai 0,
 *  accanto a ogni dato che cambia nel tempo l'ora della lettura, virgola decimale, un colore per significato. */

function Pill({ style, children, title }: { style: { color: string; background: string; borderColor?: string }; children: ReactNode; title?: string }) {
  return (
    <span
      className="inline-flex items-center whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[12px] font-medium"
      style={{ color: style.color, background: style.background, borderColor: style.borderColor ?? 'transparent' }}
      title={title}
    >
      {children}
    </span>
  )
}

const WARN_PILL = { color: C.warn.text, background: C.warn.bg, borderColor: '#F0D58A' }

export function ClassPill({ cls, children, title }: { cls: string | null | undefined; children: ReactNode; title?: string }) {
  if (!cls) return null
  return (
    <Pill style={CLASS_STYLE[cls] ?? CLASS_STYLE.Transizione} title={title}>
      {children}
    </Pill>
  )
}

// --- testata (modifiche 15, 16, 17) -----------------------------------------------------------------

const SAVE_TONE = {
  off: 'cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400',
  blue: 'border-[#2457B3] bg-[#2457B3] text-white hover:bg-[#1d4a99]',
  red: 'border-[#E8A3A3] bg-[#FDE8E8] text-[#B03030] hover:bg-[#fbd6d6]',
}

export function SaveButton({ sign, disabledReason, onClick }: { sign: EvaluatedSign | null; disabledReason?: string | null; onClick: () => void }) {
  const b = saveButtonFor(sign)
  const off = b.tone === 'off' || Boolean(disabledReason)
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={off}
      title={disabledReason ?? undefined}
      data-testid="salva-giocata"
      className={`rounded-lg border px-3 py-1.5 text-[13px] font-semibold ${disabledReason ? SAVE_TONE.off : SAVE_TONE[b.tone]}`}
    >
      <span className="hidden sm:inline">{b.text}</span>
      <span className="sm:hidden">{b.short}</span>
    </button>
  )
}

export function HeaderTypeLine({ row }: { row: MatchTableRow }) {
  const main = ['HOME', 'DRAW', 'AWAY'].map((k) => row.quotes.find((q) => q.key === k)?.quota ?? null)
  const idx = row.balance?.index
  return (
    <>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px]">
        <span className="uppercase tracking-wide text-slate-400">Tipo partita (quote Bet365)</span>
        <ClassPill cls={row.match_type} title={MATCH_TYPE_HELP}>
          {row.match_type}
        </ClassPill>
        <span className="tabular-nums text-slate-400">{main.map((v) => q2(v)).join(' · ')}</span>
        <span className="text-slate-300">|</span>
        <span className="uppercase tracking-wide text-slate-400">Equilibrio Cecchino</span>
        {row.balance?.class ? (
          <ClassPill cls={row.balance.class} title={BALANCE_HELP}>
            {row.balance.class}
            {idx != null ? ` · ${Math.round(idx)}` : ''}
          </ClassPill>
        ) : (
          <span className="text-slate-400">n.d.</span>
        )}
        {idx != null ? <span className="text-slate-400">su 100</span> : null}
      </div>
      {balanceDisagree(row.match_type, row.balance?.class) ? (
        <p className="mt-1 rounded-md px-2 py-1 text-[12px]" style={{ color: C.warn.text, background: C.warn.bg }}>
          Quote e Cecchino non concordano sull&apos;equilibrio della gara.
        </p>
      ) : null}
    </>
  )
}

export function HeaderAlerts({ row }: { row: MatchTableRow }) {
  const close = row.close_games
  const end = row.season_end
  if (!close && !end) return null
  return (
    <div className="mt-1.5 space-y-1 text-[12px] text-slate-700">
      {close ? (
        <p>
          <Pill style={WARN_PILL}>{close.label}</Pill> <span>{close.text}</span>
        </p>
      ) : null}
      {end ? (
        <p>
          <Pill style={WARN_PILL}>{end.label}</Pill> <span>{end.text}</span>
        </p>
      ) : null}
      {(end?.alerts ?? []).map((a) => (
        <p key={a.code} className="rounded-md px-2 py-0.5" style={{ color: C.warn.text, background: C.warn.bg }}>
          {a.text}
        </p>
      ))}
      <p className="text-[11px]" style={{ color: C.cmd.text }}>
        calendario e classifica letti alle {hhmm(row.computed_at)}
      </p>
    </div>
  )
}

// --- cinque riquadri (modifica 5) -------------------------------------------------------------------

function Box({ title, children, sub, time, highlight }: { title: string; children: ReactNode; sub?: ReactNode; time: ReactNode; highlight?: boolean }) {
  return (
    <div className={`flex min-w-0 flex-col items-center rounded-xl border bg-white px-2 py-2 text-center ${highlight ? 'border-2 border-[#2457B3]' : 'border-slate-200'}`}>
      <p className="text-[11px] uppercase tracking-wide text-slate-400">{title}</p>
      <div className="mt-0.5 text-[16px] font-semibold tabular-nums text-slate-900">{children}</div>
      {sub ? <p className="mt-0.5 text-[12px] text-slate-500">{sub}</p> : null}
      <p className="mt-auto pt-1 text-[11px]" style={{ color: C.cmd.text }}>
        {time}
      </p>
    </div>
  )
}

const RELIABILITY_WORD = { green: 'verde', yellow: 'gialla', red: 'rossa' } as const
const RELIABILITY_DOT = { green: C.win.fill, yellow: C.warn.dot, red: C.loss.fill } as const

export function FiveBoxes({ row }: { row: MatchTableRow }) {
  const r = row.reliability
  const ev = row.evaluation
  const sq = row.squads
  const anyKnown = Boolean(sq?.home?.injuries_known || sq?.away?.injuries_known)
  const g = row.goal_form
  const pt = row.pt_form
  const w = row.weather
  const second = ev ? (ev.second_read.done ? `2ª lettura ${hhmm(ev.second_read.at)}` : `2ª lettura ${hhmm(ev.second_read.due)}`) : '2ª lettura n.d.'
  const alerts = [g?.alert ? 'avviso Under' : null, pt?.alert ? 'avviso PT' : null].filter(Boolean)
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      <Box title="Affidabilità" sub={r ? ([...r.red, ...r.yellow][0] ?? 'tutto a posto') : 'n.d.'} time={`quote ${hhmm(row.odds_checked_at)} · ${second}`}>
        {r ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: RELIABILITY_DOT[r.level] }} />
            {RELIABILITY_WORD[r.level]}
          </span>
        ) : (
          'n.d.'
        )}
      </Box>
      <Box title="Titolari fuori" sub={anyKnown ? 'casa · ospite' : 'rosa non nota (casa · ospite)'} time={`fornitore · letto ${hhmm(row.computed_at)}`}>
        {starters(sq?.home)} · {starters(sq?.away)}
      </Box>
      <Box
        title="Gol a gara · media storica"
        sub={alerts.length ? <span style={{ color: C.warn.text }}>ultime 10 gare · {alerts.join(' · ')}</span> : 'ultime 10 gare · nessun avviso'}
        time={`calcolata ${hhmm(row.computed_at)}`}
      >
        {dec1(g?.avg)} <span className="text-[12px] font-normal text-slate-500">PT {dec1(pt?.avg)}</span>
      </Box>
      <Box
        title="Meteo al via"
        highlight
        sub={w?.kickoff ? `pioggia ${dec1(w.kickoff.precipitation)} mm · vento ${Math.round(w.kickoff.wind ?? 0)} km/h` : 'senza città o previsione'}
        time={w?.fetched_at && w.status === 'ok' ? `previsione delle ${hhmm(w.fetched_at)}` : 'previsione n.d.'}
      >
        {w?.kickoff ? (
          <span title={w.kickoff.text}>
            {w.kickoff.icon} {w.kickoff.temperature != null ? `${Math.round(w.kickoff.temperature)}°C` : 'n.d.'}
          </span>
        ) : (
          'n.d.'
        )}
      </Box>
      <Box title="Segni di oggi" time={`sulla quota delle ${readTime(ev)}`}>
        {ev ? (
          <span className="block text-left text-[13px] leading-5">
            <span className="block" style={{ color: C.win.text }}>
              <b>{ev.counts.playable}</b> giocabili
            </span>
            <span className="block" style={{ color: C.warn.text }}>
              <b>{ev.counts.check}</b> da verificare
            </span>
            <span className="block" style={{ color: C.loss.text }}>
              <b>{ev.counts.blocked}</b> bloccati
            </span>
          </span>
        ) : (
          'n.d.'
        )}
      </Box>
    </div>
  )
}

// --- «Segni · decidi qui» (modifiche 1, 2, 3) -------------------------------------------------------

const GROUP_ORDER = ['ESITO FINALE', 'DOPPIA CHANCE', 'UNDER / OVER', 'PRIMO TEMPO', 'GOL PRIMO TEMPO']

function StatePill({ s }: { s: EvaluatedSign }) {
  const reason = s.reasons[0]?.text
  const style: Record<SignState, { color: string; background: string }> = {
    playable: { color: C.win.text, background: C.win.bg },
    check: { color: C.warn.text, background: C.warn.bg },
    blocked: { color: C.loss.text, background: C.loss.bg },
    out: { color: C.even.text, background: C.even.bg },
  }
  const text = s.state === 'playable' ? 'giocabile' : s.state === 'check' ? (reason ?? 'da verificare') : s.state === 'blocked' ? (s.reasons.map((r) => r.text).join(' · ') || 'bloccato') : (reason ?? 'fuori fascia')
  return (
    <span className="inline-block rounded-md px-1.5 py-0.5 text-[12px] font-medium" style={style[s.state]}>
      {s.state === 'check' ? `da verificare · ${text}` : text}
    </span>
  )
}

function SignRow({ s, selected, onPick }: { s: EvaluatedSign; selected: boolean; onPick?: () => void }) {
  const pickable = Boolean(onPick) && s.state !== 'out'
  return (
    <tr className={`border-b border-slate-100 ${selected ? 'bg-[#E3EDFF]' : ''}`}>
      <td className="w-10 py-1.5 pl-2 text-center">
        {pickable ? (
          s.state === 'blocked' ? (
            <button type="button" onClick={onPick} title="Segno bloccato: si salva solo con «Registra eccezione»" aria-label={`Scegli ${s.label} (bloccato)`} aria-pressed={selected}>
              🔒
            </button>
          ) : (
            <input type="radio" name="segno-scelto" checked={selected} onChange={onPick} aria-label={`Scegli ${s.label}`} />
          )
        ) : null}
      </td>
      <td className={`py-1.5 pr-2 ${s.state === 'playable' || s.state === 'check' ? 'font-semibold text-slate-900' : 'text-slate-600'}`}>{signLabel(s.label)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums" style={{ background: C.market.bg }}>
        {s.q_source === 't75' ? (
          <span title={`quota del mattino ${q2(s.morning)}, seconda lettura alle ${hhmm(s.q_at)}`}>
            <span className="text-slate-400">{q2(s.morning)} → </span>
            <b className="text-slate-900">{q2(s.q)}</b>
            <span className="ml-1 text-[11px] text-slate-500">{signedPct(s.change, 1)}</span>
          </span>
        ) : (
          <b className="text-slate-900">{q2(s.q)}</b>
        )}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums text-slate-600" style={{ background: C.market.bg }}>
        {pct0(s.prob_book)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums" style={{ background: C.model.bg, color: C.model.text }}>
        {q2(s.quota_cecchino)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums" style={{ background: C.model.bg, color: C.model.text }}>
        {pct0(s.prob_cecchino)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums" style={{ background: C.model.bg, color: C.model.text }}>
        {signedPct(s.value)}
      </td>
      <td className="py-1.5 pl-2">
        <StatePill s={s} />
        {s.notes.map((n) => (
          <span key={n.code} className="mt-0.5 block text-[11px]" style={{ color: C.warn.text }} title="Solo un avviso: non blocca (prova storica del 26/11/2026)">
            avviso · {n.text}
          </span>
        ))}
      </td>
    </tr>
  )
}

function GroupRow({ label }: { label: string }) {
  return (
    <tr className="bg-slate-50">
      <td colSpan={8} className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </td>
    </tr>
  )
}

export function SignsTable({
  evaluation,
  selectedKey,
  onPick,
}: {
  evaluation: RowEvaluation | undefined
  selectedKey: string | null
  onPick?: (key: string) => void
}) {
  const [showOut, setShowOut] = useState(false)
  if (!evaluation || !evaluation.signs.length) {
    return (
      <section className="rounded-xl border border-slate-200 p-3">
        <p className="text-[12px] font-semibold uppercase tracking-wide text-slate-500">Segni · decidi qui</p>
        <p className="mt-1 text-[13px] text-slate-500">Quote n.d. per questa gara.</p>
      </section>
    )
  }
  const live = evaluation.signs.filter((s) => s.state === 'playable' || s.state === 'check')
  const blocked = evaluation.signs.filter((s) => s.state === 'blocked')
  const out = evaluation.signs.filter((s) => s.state === 'out')
  const groups = GROUP_ORDER.map((g) => ({ g, rows: live.filter((s) => s.group === g) })).filter((x) => x.rows.length)
  const extra = live.filter((s) => !GROUP_ORDER.includes(s.group))
  if (extra.length) groups.push({ g: 'ALTRI', rows: extra })
  const pick = onPick ? (key: string) => () => onPick(key) : undefined
  return (
    <section className="rounded-xl border border-slate-200 p-3">
      <p className="text-[12px] font-semibold uppercase tracking-wide text-slate-500">Segni · decidi qui</p>
      <div className="mt-1.5 overflow-x-auto">
        <table className="w-full min-w-[640px] text-[13px]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wide text-slate-400">
              <th colSpan={2} />
              <th colSpan={2} className="px-2 pt-1 text-left font-semibold" style={{ background: C.market.bg }}>
                Mercato · Bet365
              </th>
              <th colSpan={3} className="px-2 pt-1 text-left font-semibold" style={{ background: C.model.bg, color: C.model.text }}>
                Modello · Cecchino
              </th>
              <th />
            </tr>
            <tr className="border-b border-slate-200 text-[11px] text-slate-400">
              <th className="py-1 pl-2 text-left font-medium">Scegli</th>
              <th className="py-1 pr-2 text-left font-medium">Segno</th>
              <th className="px-2 py-1 text-right font-medium" style={{ background: C.market.bg }}>
                quota
              </th>
              <th className="px-2 py-1 text-right font-medium" style={{ background: C.market.bg }}>
                prob. senza margine
              </th>
              <th className="px-2 py-1 text-right font-medium" style={{ background: C.model.bg }}>
                quota
              </th>
              <th className="px-2 py-1 text-right font-medium" style={{ background: C.model.bg }}>
                prob.
              </th>
              <th className="px-2 py-1 text-right font-medium" style={{ background: C.model.bg }}>
                valore secondo il Cecchino
              </th>
              <th className="py-1 pl-2 text-left font-medium">Stato</th>
            </tr>
          </thead>
          <tbody>
            {groups.map(({ g, rows }) => (
              <SignGroup key={g} label={g} rows={rows} selectedKey={selectedKey} pick={pick} />
            ))}
            {blocked.length ? <SignGroup label="BLOCCATI" rows={blocked} selectedKey={selectedKey} pick={pick} /> : null}
            {showOut ? out.map((s) => <SignRow key={s.key} s={s} selected={false} />) : null}
          </tbody>
        </table>
      </div>
      {out.length ? (
        <button type="button" className="mt-1 text-[13px] font-medium" style={{ color: C.cmd.text }} onClick={() => setShowOut((v) => !v)}>
          {showOut ? '▾' : '▸'} altri {out.length} segni fuori fascia o da evitare
        </button>
      ) : null}
      <p className="mt-1 text-[12px] text-slate-500">
        Grigio = mercato (il dato più affidabile). Azzurro = modello Cecchino (solo controllo). Quote Bet365 delle {readTime(evaluation)}.
      </p>
    </section>
  )
}

function SignGroup({ label, rows, selectedKey, pick }: { label: string; rows: EvaluatedSign[]; selectedKey: string | null; pick?: (key: string) => () => void }) {
  return (
    <>
      <GroupRow label={label} />
      {rows.map((s) => (
        <SignRow key={s.key} s={s} selected={selectedKey === s.key} onPick={pick ? pick(s.key) : undefined} />
      ))}
    </>
  )
}

// --- forma (modifica 6) -----------------------------------------------------------------------------

const LEVEL_TEXT: Record<DiffLevel, string> = { strong: '▲ più forte', even: '● alla pari', weak: '▼ più debole' }

function ppg(v: number | null | undefined): string {
  if (v == null) return ''
  const t = Math.abs(v).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v > 0 ? `+${t}` : v < 0 ? `−${t}` : t
}

function ScoreBox({ outcome, score, framed, title }: { outcome: TableOutcome | null; score: string | null; framed: boolean; title: string }) {
  return (
    <div
      title={title}
      className="flex h-7 items-center justify-center rounded-md text-[13px] font-semibold tabular-nums text-white"
      style={{
        background: outcome ? OUTCOME_FILL[outcome] : '#E5E7EB',
        outline: framed ? `2px dashed ${C.cmd.text}` : undefined,
        outlineOffset: framed ? '1px' : undefined,
      }}
    >
      {score ?? 'n.d.'}
    </div>
  )
}

function pointsAgainst(results: TableGame[]) {
  const by: Record<DiffLevel, { p: number; n: number }> = { strong: { p: 0, n: 0 }, even: { p: 0, n: 0 }, weak: { p: 0, n: 0 } }
  for (const g of results) {
    if (!g.level || !g.ft_outcome) continue
    by[g.level].n += 1
    by[g.level].p += g.ft_outcome === 'V' ? 3 : g.ft_outcome === 'N' ? 1 : 0
  }
  return by
}

function TeamForm({ team, venue, block }: { team: string; venue: string; block: TableBlock }) {
  if (!block.enough) {
    return (
      <div className="text-[13px] text-slate-500">
        <b className="text-slate-900">{team}</b> · {venue}: meno di 3 gare in stagione ({block.games})
      </div>
    )
  }
  const results = block.results
  const vs = pointsAgainst(results)
  return (
    <div className="grid gap-3 lg:grid-cols-[150px_minmax(0,1fr)_190px]">
      <div className="text-[13px]">
        <p className="font-semibold text-slate-900">{team}</p>
        <p className="text-slate-500">
          {venue} · {block.points} punti su {block.max_points}
        </p>
        <p className="text-slate-500">
          gol {block.scored}-{block.conceded} · PT {block.ht_scored}-{block.ht_conceded}
        </p>
      </div>
      <div className="grid grid-cols-[48px_repeat(5,minmax(0,1fr))] items-center gap-x-1.5 gap-y-1 overflow-x-auto">
        <span className="text-[11px] font-semibold text-slate-400">PT</span>
        {results.map((g, i) => (
          <ScoreBox key={`pt-${i}`} outcome={g.ht_outcome} score={g.ht} framed={Boolean(g.ht_outcome && g.ft_outcome && g.ht_outcome !== g.ft_outcome)} title={`${ddmm(g.date)} PT ${g.ht ?? 'n.d.'}`} />
        ))}
        {Array.from({ length: Math.max(0, 5 - results.length) }).map((_, i) => (
          <span key={`e1-${i}`} />
        ))}
        <span className="text-[11px] font-semibold text-slate-400">FINALE</span>
        {results.map((g, i) => (
          <ScoreBox key={`ft-${i}`} outcome={g.ft_outcome} score={g.ft} framed={Boolean(g.ht_outcome && g.ft_outcome && g.ht_outcome !== g.ft_outcome)} title={`${ddmm(g.date)} finale ${g.ft ?? 'n.d.'}`} />
        ))}
        {Array.from({ length: Math.max(0, 5 - results.length) }).map((_, i) => (
          <span key={`e2-${i}`} />
        ))}
        <span />
        {results.map((g, i) => (
          <div key={`o-${i}`} className="min-w-0 text-center text-[12px] leading-4">
            <p className="truncate text-slate-700" title={`${ddmm(g.date)} ${g.home ? 'in casa' : 'fuori'}${g.diff != null ? ` · ${ppg(g.diff)} punti a partita alla data` : ''}`}>
              {g.opponent ?? '?'} {g.opponent_rank ? `${g.opponent_rank}ª` : ''}
            </p>
            <p style={{ color: C.level }}>{g.level ? LEVEL_TEXT[g.level] : 'n.d.'}</p>
          </div>
        ))}
      </div>
      <div className="rounded-lg bg-slate-50 px-2.5 py-2 text-[12px] text-slate-700">
        <p className="font-semibold text-slate-800">Punti fatti contro avversarie</p>
        {(['strong', 'even', 'weak'] as DiffLevel[]).map((lv) => (
          <p key={lv} className="tabular-nums">
            {lv === 'strong' ? 'più forti' : lv === 'even' ? 'alla pari' : 'più deboli'}{' '}
            {vs[lv].n ? (
              <>
                <b>
                  {vs[lv].p} su {3 * vs[lv].n}
                </b>{' '}
                <span className="text-slate-400">{vs[lv].n === 1 ? '1 gara' : `${vs[lv].n} gare`}</span>
              </>
            ) : (
              <span className="text-slate-400">nessuna gara</span>
            )}
          </p>
        ))}
      </div>
    </div>
  )
}

export function FormBlock({ row }: { row: MatchTableRow }) {
  const [mode, setMode] = useState<'cf' | 'tot'>('cf')
  const g = row.goal_form
  const pt = row.pt_form
  const lines =
    mode === 'cf'
      ? [
          { team: row.home_team, venue: 'in casa', block: row.blocks.forma_casa },
          { team: row.away_team, venue: 'fuori', block: row.blocks.forma_fuori },
        ]
      : [
          { team: row.home_team, venue: 'totale', block: row.blocks.forma_totale_casa },
          { team: row.away_team, venue: 'totale', block: row.blocks.forma_totale_fuori },
        ]
  return (
    <section className="rounded-xl border border-slate-200 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12px] font-semibold uppercase tracking-wide text-slate-500">Forma · ultime 5</p>
        <div className="flex items-center gap-2 text-[12px] text-slate-500">
          <span>
            <span className="rounded px-1" style={{ outline: `2px dashed ${C.cmd.text}` }}>
              cornice
            </span>{' '}
            = il risultato cambia dal PT al finale
          </span>
          <div className="inline-flex overflow-hidden rounded-lg border border-slate-200" role="group" aria-label="Forma">
            {(
              [
                ['cf', 'Casa / Fuori'],
                ['tot', 'Totale'],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                onClick={() => setMode(k)}
                aria-pressed={mode === k}
                className={`px-2.5 py-1 text-[12px] font-medium ${mode === k ? 'bg-[#2457B3] text-white' : 'bg-white text-slate-700'}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-2 space-y-3">
        {lines.map((l) => (
          <TeamForm key={l.team + l.venue} team={l.team} venue={l.venue} block={l.block} />
        ))}
      </div>
      <p className="mt-2 text-[12px] text-slate-500">
        «Più forte» o «più debole»: alla data della gara la squadra avversaria faceva almeno 0,3 punti a partita in più o in meno; altrimenti «alla pari» (soglia
        provvisoria).
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl bg-slate-800 px-3 py-2.5 text-white">
        <p className="text-[11px] uppercase tracking-wide opacity-80">Medie · ultime 10 gare delle due squadre</p>
        <Stat label="Gol a gara" value={dec1(g?.avg)} />
        <Stat label="Gol PT" value={dec1(pt?.avg)} />
        <Stat label="X PT" value={pt ? `${pt.x_pct}%` : 'n.d.'} />
        <Stat label="Under 1,5 PT" value={pt ? `${pt.u15_pct}%` : 'n.d.'} />
        {g?.alert ? <Pill style={WARN_PILL}>avviso Under</Pill> : null}
        {pt?.alert ? <Pill style={WARN_PILL}>avviso PT</Pill> : null}
      </div>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide opacity-70">{label}</p>
      <p className="text-[20px] font-semibold tabular-nums">{value}</p>
    </div>
  )
}

// --- contesto chiuso (modifiche 7, 9, 13) -----------------------------------------------------------

function Row({ title, summary, children }: { title: string; summary: string; children: ReactNode }) {
  return (
    <details className="group border-b border-slate-100 py-1.5 last:border-b-0">
      <summary className="cursor-pointer list-none text-[13px]">
        <span className="font-semibold text-slate-800">
          <span className="inline-block w-3 group-open:rotate-90">▸</span> {title}
        </span>{' '}
        <span className="text-slate-400">· {summary}</span>
      </summary>
      <div className="mt-2 pl-4">{children}</div>
    </details>
  )
}

function TeamCalendar({ team, s }: { team: string; s: TeamSchedule | null | undefined }) {
  const comp = (g: NonNullable<TeamSchedule['last']>) => (g.league_match ? 'campionato' : (g.competition ?? 'altra competizione'))
  return (
    <div className="text-[13px] text-slate-700">
      <p className="font-semibold text-slate-900">{team}</p>
      {!s ? (
        <p className="text-slate-400">calendario n.d.</p>
      ) : (
        <>
          <p>
            Ultima: {s.last ? `${ddmm(s.last.date)} · ${comp(s.last)} · ${s.last.home ? 'in casa con' : 'fuori con'} ${s.last.opponent ?? '?'} (${s.last.days} giorni fa)` : 'n.d.'}
          </p>
          <p>
            Prossima: {s.next ? `${ddmm(s.next.date)} · ${comp(s.next)} · ${s.next.home ? 'in casa con' : 'fuori con'} ${s.next.opponent ?? '?'} (tra ${s.next.days} giorni)` : 'n.d.'}
          </p>
          <p className="text-[12px] text-slate-500">
            Gare negli ultimi 7 giorni: {s.games_7} · negli ultimi 14: {s.games_14}
          </p>
        </>
      )}
    </div>
  )
}

const OUTCOME_PILL: Record<TableOutcome, { color: string; background: string }> = {
  V: { color: '#FFFFFF', background: C.win.fill },
  N: { color: '#FFFFFF', background: C.even.fill },
  P: { color: '#FFFFFF', background: C.loss.fill },
}

/** Ultime gare con i titolari mancanti (modifica 7): rosa n.d. quando non la conosciamo, mai «0 titolari». */
export function SquadHistory({ team, s }: { team: string; s: TeamSquad | undefined }) {
  if (!s) return <p className="text-[13px] text-slate-400">{team}: formazioni n.d.</p>
  const rows = s.history ?? []
  const known = rows.filter((h) => h.rosa)
  const wins = rows.filter((h) => h.ft_outcome === 'V').length
  const draws = rows.filter((h) => h.ft_outcome === 'N').length
  const losses = rows.filter((h) => h.ft_outcome === 'P').length
  const gf = rows.reduce((t, h) => t + (h.ft ? Number(h.ft.split('-')[0]) : 0), 0)
  const ga = rows.reduce((t, h) => t + (h.ft ? Number(h.ft.split('-')[1]) : 0), 0)
  const avgOut = known.length ? known.reduce((t, h) => t + (h.rosa?.missing ?? 0), 0) / known.length : null
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <p className="text-[13px] font-semibold text-slate-900">{team} · ultime {rows.length} gare</p>
      <p className="text-[12px] text-slate-500">
        Oggi: indisponibili{' '}
        {s.injuries_known ? `${s.injured.length} (${s.injured.map((i) => `${i.name ?? '?'}${i.starter ? ', titolare' : ''}`).join('; ')})` : 'n.d. (il fornitore non li dà per questa gara)'}
        {' · '}titolari fuori {s.injuries_known && s.habitual ? s.missing_starters : 'n.d.'}
      </p>
      <table className="mt-1 w-full text-[13px] tabular-nums">
        <tbody>
          {rows.map((h, i) => (
            <tr key={i} className="border-b border-slate-100">
              <td className="w-12 py-1 text-slate-500">{ddmm(h.date)}</td>
              <td className="w-5 py-1 text-slate-400">{h.home == null ? '' : h.home ? 'C' : 'F'}</td>
              <td className={`py-1 ${h.level === 'strong' ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>{h.opponent ?? '?'}</td>
              <td className="w-10 py-1 text-slate-400">{h.opponent_rank ? `${h.opponent_rank}°` : ''}</td>
              <td className="w-24 py-1">
                {h.ft_outcome ? (
                  <span className="mr-1 inline-block rounded px-1 text-[11px] font-bold" style={OUTCOME_PILL[h.ft_outcome]}>
                    {h.ft_outcome}
                  </span>
                ) : null}
                <b>{h.ft ?? 'n.d.'}</b>
              </td>
              <td className="w-16 py-1 text-slate-400">PT {h.ht ?? 'n.d.'}</td>
              <td className="py-1 text-right" style={{ color: h.rosa ? (h.rosa.complete ? C.win.text : C.loss.text) : '#94A3B8' }} title={h.rosa?.players?.filter(Boolean).join(', ')}>
                {h.rosa ? (h.rosa.complete ? 'rosa completa' : h.rosa.text) : 'rosa n.d.'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[12px] text-slate-500">
        {wins}V {draws}N {losses}P · gol {gf}-{ga} · titolari fuori in media {avgOut == null ? 'n.d.' : dec1(avgOut)}
      </p>
    </div>
  )
}

/** Movimento della quota (modifica 9): una freccia e la variazione, niente grafico; non si chiama CLV. */
export function OddsMoveTable({ row }: { row: MatchTableRow }) {
  const rows = moveRows(row)
  const at = row.evaluation?.second_read
  return (
    <div>
      <p className="text-[13px] font-semibold text-slate-800">Movimento quota Bet365 · mattino → −75&apos;</p>
      <table className="mt-1 w-full max-w-xl text-[13px] tabular-nums">
        <thead>
          <tr className="border-b border-slate-200 text-[11px] text-slate-400">
            <th className="py-1 text-left font-medium">Segno</th>
            <th className="py-1 text-right font-medium">{hhmm(row.odds_checked_at)}</th>
            <th />
            <th className="py-1 text-right font-medium">−75&apos;</th>
            <th className="py-1 pl-3 text-left font-medium">Variazione</th>
            <th className="py-1 text-left font-medium">Verso il Cecchino?</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-b border-slate-100">
              <td className="py-1 text-slate-700">{r.label}</td>
              <td className="py-1 text-right">{q2(r.morning)}</td>
              <td className="px-2 py-1 text-slate-400">→</td>
              <td className="py-1 text-right font-semibold">{r.later == null ? 'n.d.' : q2(r.later)}</td>
              <td className="py-1 pl-3" style={{ color: r.change == null || Math.abs(r.change) < 0.0005 ? C.even.text : r.change > 0 ? C.win.text : C.loss.text }}>
                {r.change == null ? 'n.d.' : Math.abs(r.change) < 0.0005 ? 'ferma' : signedPct(r.change, 1)}
              </td>
              <td className="py-1 text-slate-600">{r.later == null ? 'n.d.' : r.toward == null ? '—' : r.toward ? 'sì' : 'no'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[12px] text-slate-500">
        {at?.done ? `Letture delle ${hhmm(row.odds_checked_at)} e delle ${hhmm(at.at)}.` : `La seconda lettura arriva alle ${hhmm(at?.due)} (75 minuti prima del via): fino ad allora «n.d.».`}
      </p>
    </div>
  )
}

function cardsAvg(c: TableCards): string {
  return c.available ? dec1(c.own_avg) : 'n.d.'
}

export function ContextSection({ row, legend, extra }: { row: MatchTableRow; legend: ReactNode; extra?: ReactNode }) {
  const sq = row.squads
  const anyKnown = Boolean(sq?.home?.injuries_known || sq?.away?.injuries_known)
  const w = row.weather
  const hours = w?.hours ?? []
  const squadsSummary = anyKnown
    ? `titolari fuori ${starters(sq?.home)} · ${starters(sq?.away)} · letto ${hhmm(row.computed_at)}`
    : `rosa non nota per entrambe (n.d., non 0) · letto ${hhmm(row.computed_at)}`
  return (
    <section className="rounded-xl border border-slate-200 p-3">
      <p className="text-[12px] font-semibold uppercase tracking-wide text-slate-500">Contesto · si apre a richiesta</p>
      <div className="mt-1">
        <Row title="Calendario" summary={calendarSummary(row)}>
          <div className="grid gap-3 sm:grid-cols-2">
            <TeamCalendar team={row.home_team} s={row.schedule?.home} />
            <TeamCalendar team={row.away_team} s={row.schedule?.away} />
          </div>
        </Row>
        <Row title="Indisponibili e formazioni" summary={squadsSummary}>
          <div className="grid gap-3 lg:grid-cols-2">
            <SquadHistory team={row.home_team} s={sq?.home} />
            <SquadHistory team={row.away_team} s={sq?.away} />
          </div>
        </Row>
        <Row title="Movimento quote" summary={moveSummary(row)}>
          <OddsMoveTable row={row} />
        </Row>
        <Row title="Ammonizioni" summary={`${cardsAvg(row.yellows.home)} e ${cardsAvg(row.yellows.away)} a gara (ultime 5)`}>
          <div className="space-y-0.5 text-[13px] text-slate-700">
            {(
              [
                [row.home_team, row.yellows.home],
                [row.away_team, row.yellows.away],
              ] as [string, TableCards][]
            ).map(([team, c]) => (
              <p key={team}>
                {team}:{' '}
                {c.available ? `${dec1(c.own_avg)} fatti e ${dec1(c.opponents_avg)} subiti a gara (${c.own} e ${c.opponents} in ${c.games} gare)` : 'n.d.'}
              </p>
            ))}
          </div>
        </Row>
        <Row
          title="Meteo ora per ora"
          summary={hours.length ? `dalle ${hhmm(hours[0].at)} alle ${hhmm(hours[hours.length - 1].at)} · previsione delle ${hhmm(w?.fetched_at)}` : 'n.d.'}
        >
          {hours.length ? (
            <table className="w-full max-w-lg text-[13px] tabular-nums">
              <tbody>
                {hours.map((h) => (
                  <tr key={h.at} className="border-b border-slate-100">
                    <td className="py-1 text-slate-500">{hhmm(h.at)}</td>
                    <td className="py-1">
                      {h.icon} {h.text}
                    </td>
                    <td className="py-1 text-right">{h.temperature != null ? `${Math.round(h.temperature)}°C` : 'n.d.'}</td>
                    <td className="py-1 text-right">pioggia {dec1(h.precipitation)} mm</td>
                    <td className="py-1 text-right">vento {h.wind != null ? Math.round(h.wind) : 'n.d.'} km/h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-[13px] text-slate-500">Meteo n.d.: manca la città dello stadio o la previsione di Open-Meteo. È solo un&apos;informazione e non cambia nessuno stato.</p>
          )}
        </Row>
        <Row title="Legenda" summary="come si leggono i numeri">
          {legend}
        </Row>
        {extra}
      </div>
    </section>
  )
}
