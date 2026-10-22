import { useEffect, useMemo, useState } from 'react'
import {
  todayBadgeActive,
  todayBadgeMuted,
  todayBadgeOk,
  todayCard,
  todayCardPadding,
  todaySectionSubtitle,
  todaySectionTitle,
  todaySkeleton,
} from '../components/cecchino/cecchinoTodayStyles'
import {
  fetchEnginesCompare,
  fetchV5Day,
  type EngineMeta,
  type EnginesCompare,
  type EngineTotal,
  type V5Day,
  type V5Play,
} from '../lib/cecchinoV5Api'

const PERIODS = [7, 30, 90] as const
const LABEL = 'text-[13px] text-slate-500'
const CELL = 'px-2 py-1.5 text-right tabular-nums'

function romeToday(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome' }).format(new Date())
}

function shiftDay(day: string, delta: number): string {
  const d = new Date(`${day}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + delta)
  return d.toISOString().slice(0, 10)
}

function num(v: number | null | undefined, digits = 2): string {
  return v == null ? '–' : v.toLocaleString('it-IT', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function signed(v: number | null | undefined, digits = 1, suffix = ''): string {
  if (v == null) return '–'
  return `${v > 0 ? '+' : ''}${num(v, digits)}${suffix}`
}

function tone(v: number | null | undefined): string {
  if (v == null || v === 0) return 'text-slate-600'
  return v > 0 ? 'text-emerald-700' : 'text-rose-700'
}

function kickoff(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit' })
}

function StatusBadge({ meta }: { meta: Pick<EngineMeta, 'v5_status'> }) {
  if (!meta.v5_status) return null
  return meta.v5_status === 'consigliata' ? (
    <span className={todayBadgeOk}>consigliata</span>
  ) : (
    <span className={todayBadgeMuted}>osservazione</span>
  )
}

function ResultBadge({ play }: { play: V5Play }) {
  if (!play.result) return <span className={todayBadgeActive}>aperta</span>
  if (play.result === 'vinta') return <span className={todayBadgeOk}>vinta</span>
  return <span className={todayBadgeMuted}>{play.result}</span>
}

function TotalsTable({ totals }: { totals: EngineTotal[] }) {
  if (!totals.length) return <p className="text-sm text-slate-500">Nessuna giocata conclusa nel periodo.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-sm">
        <thead>
          <tr className={`${LABEL} border-b border-slate-200`}>
            <th className="px-2 py-1.5 text-left font-medium">Motore</th>
            <th className="px-2 py-1.5 text-right font-medium">Giocate</th>
            <th className="px-2 py-1.5 text-right font-medium">Vinte</th>
            <th className="px-2 py-1.5 text-right font-medium">Quota media</th>
            <th className="px-2 py-1.5 text-right font-medium">% per andare in pari</th>
            <th className="px-2 py-1.5 text-right font-medium">Profitto (unità)</th>
            <th className="px-2 py-1.5 text-right font-medium">ROI</th>
            <th className="px-2 py-1.5 text-right font-medium">Forbice 90%</th>
            <th className="px-2 py-1.5 text-right font-medium">CLV medio</th>
          </tr>
        </thead>
        <tbody>
          {totals.map((t) => (
            <tr key={t.engine} className="border-b border-slate-100 last:border-0">
              <td className="px-2 py-1.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium text-slate-900">{t.label}</span>
                  <StatusBadge meta={t} />
                </div>
                <div className={LABEL}>{t.family}</div>
              </td>
              <td className={CELL}>{t.plays}</td>
              <td className={CELL}>
                {t.won} <span className="text-slate-400">({num(t.win_pct, 1)}%)</span>
              </td>
              <td className={CELL}>{num(t.avg_quota)}</td>
              <td className={CELL}>{num(t.break_even_pct, 1)}%</td>
              <td className={`${CELL} font-semibold ${tone(t.profit)}`}>{signed(t.profit, 2)}</td>
              <td className={`${CELL} ${tone(t.roi_pct)}`}>{signed(t.roi_pct, 1, '%')}</td>
              <td className={`${CELL} text-slate-500`}>
                {t.roi_low_pct == null ? '–' : `${signed(t.roi_low_pct, 1)} / ${signed(t.roi_high_pct, 1)}%`}
              </td>
              <td className={`${CELL} ${tone(t.avg_clv_pct)}`}>{signed(t.avg_clv_pct, 2, '%')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DailyTable({ data }: { data: EnginesCompare }) {
  if (!data.daily.length) return <p className="text-sm text-slate-500">Nessuna giornata con giocate concluse.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className={`${LABEL} border-b border-slate-200`}>
            <th className="sticky left-0 bg-white px-2 py-1.5 text-left font-medium">Giorno</th>
            {data.engines.map((e) => (
              <th key={e.engine} className="whitespace-nowrap px-2 py-1.5 text-right font-medium">
                {e.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.daily.map((row) => (
            <tr key={row.day} className="border-b border-slate-100 last:border-0">
              <td className="sticky left-0 whitespace-nowrap bg-white px-2 py-1.5 tabular-nums text-slate-700">
                {new Date(`${row.day}T12:00:00Z`).toLocaleDateString('it-IT', { weekday: 'short', day: '2-digit', month: '2-digit' })}
              </td>
              {data.engines.map((e) => {
                const c = row.engines[e.engine]
                return (
                  <td key={e.engine} className={`${CELL} whitespace-nowrap`}>
                    {c ? (
                      <>
                        <span className={`font-semibold ${tone(c.profit)}`}>{signed(c.profit, 2)}</span>{' '}
                        <span className="text-[13px] text-slate-400">
                          {c.won}/{c.plays}
                        </span>
                      </>
                    ) : (
                      <span className="text-slate-300">·</span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function V5DayBlock({ day, onDay }: { day: string; onDay: (d: string) => void }) {
  const [data, setData] = useState<V5Day | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    setData(null)
    setError(null)
    fetchV5Day(day)
      .then((d) => alive && setData(d))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      alive = false
    }
  }, [day])

  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className={todaySectionTitle}>Liste V5 del giorno</h2>
          <p className={todaySectionSubtitle}>
            Liste sigillate: una giocata pubblicata non cambia più. Quota migliore tra Bet365 e Betfair al momento della lista.
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <button type="button" className="rounded-lg border border-slate-200 px-2.5 py-1 text-sm hover:bg-slate-50" onClick={() => onDay(shiftDay(day, -1))}>
            ‹
          </button>
          <span className="min-w-[110px] text-center text-sm font-medium tabular-nums text-slate-800">
            {new Date(`${day}T12:00:00Z`).toLocaleDateString('it-IT', { weekday: 'short', day: '2-digit', month: 'long' })}
          </span>
          <button type="button" className="rounded-lg border border-slate-200 px-2.5 py-1 text-sm hover:bg-slate-50" onClick={() => onDay(shiftDay(day, 1))}>
            ›
          </button>
        </div>
      </div>
      {error ? <p className="text-sm text-rose-700">Errore: {error}</p> : null}
      {!data && !error ? <div className={`${todaySkeleton} h-24`} /> : null}
      {data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.specialists.map((s) => (
            <div key={s.key} className="rounded-lg border border-slate-200 p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-slate-900">{s.label}</span>
                <StatusBadge meta={{ v5_status: s.status }} />
                <span className={`${LABEL} ml-auto`}>
                  {s.plays.length} giocate
                  {s.summary.plays ? ` · ${s.summary.won}/${s.summary.plays} vinte · ${signed(s.summary.profit, 2)} u` : ''}
                </span>
              </div>
              {s.plays.length === 0 ? (
                <p className="text-[13px] text-slate-400">Nessuna giocata.</p>
              ) : (
                <ul className="space-y-1.5">
                  {s.plays.map((p) => (
                    <li key={p.id} className="text-sm">
                      <div className="flex flex-wrap items-center gap-x-2">
                        <span className="tabular-nums text-slate-400">{kickoff(p.kickoff_at)}</span>
                        <span className="text-slate-800">
                          {p.home_team} – {p.away_team}
                        </span>
                        {p.score ? <span className="tabular-nums text-slate-500">{p.score}</span> : null}
                        <span className="ml-auto">
                          <ResultBadge play={p} />
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-2 text-[13px] text-slate-500">
                        <span className="font-medium text-slate-700">{p.label}</span>
                        <span>
                          quota <b className="tabular-nums text-slate-800">{num(p.quota)}</b> {p.bookmaker}
                        </span>
                        <span>prob. {num(100 * p.probability, 0)}%</span>
                        {p.expected != null ? <span>attesi {num(p.expected, 1)}</span> : null}
                        {p.closing_quota != null ? (
                          <span className={tone(p.clv)}>
                            chiusura {num(p.closing_quota)} ({signed(p.clv == null ? null : 100 * p.clv, 1, '%')})
                          </span>
                        ) : null}
                        <span className="text-slate-400">{p.competition}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export function EnginesComparePage() {
  const [days, setDays] = useState<number>(30)
  const [day, setDay] = useState<string>(romeToday())
  const [data, setData] = useState<EnginesCompare | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setData(null)
    setError(null)
    fetchEnginesCompare(days)
      .then((d) => alive && setData(d))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      alive = false
    }
  }, [days])

  const errors = useMemo(() => Object.entries(data?.errors ?? {}), [data])

  return (
    <div className="space-y-5 text-sm">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Confronto motori</h1>
          <p className={todaySectionSubtitle}>
            Tutti i motori sullo stesso metro: 1 unità a giocata, solo giocate concluse (vinte o perse). La forbice al 90% dice
            quanto il ROI può essere frutto del caso.
          </p>
        </div>
        <div className="flex gap-1.5">
          {PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setDays(p)}
              className={`rounded-lg border px-3 py-1 text-sm ${p === days ? 'border-blue-400 bg-blue-50 text-blue-800' : 'border-slate-200 hover:bg-slate-50'}`}
            >
              {p} giorni
            </button>
          ))}
        </div>
      </header>

      <V5DayBlock day={day} onDay={setDay} />

      <section className={`${todayCard} ${todayCardPadding}`}>
        <h2 className={todaySectionTitle}>Totali del periodo</h2>
        <p className={`${todaySectionSubtitle} mb-3`}>
          {data ? `Dal ${data.date_from} al ${data.date_to}. ` : ''}
          Un motore con più giocate per partita (indice, segnali) non è confrontabile 1:1 con uno a una giocata per partita
          (Bet Builder, in evidenza, V4, V5).
        </p>
        {error ? <p className="text-sm text-rose-700">Errore: {error}</p> : null}
        {!data && !error ? (
          <>
            <p className="mb-2 text-[13px] text-slate-500">Calcolo in corso: la prima volta per un periodo può richiedere un minuto.</p>
            <div className={`${todaySkeleton} h-48`} />
          </>
        ) : null}
        {data ? <TotalsTable totals={data.totals} /> : null}
        {errors.length ? (
          <p className="mt-2 text-[13px] text-amber-700">
            Motori non letti: {errors.map(([k]) => k).join(', ')}
          </p>
        ) : null}
      </section>

      <section className={`${todayCard} ${todayCardPadding}`}>
        <h2 className={todaySectionTitle}>Giorno per giorno</h2>
        <p className={`${todaySectionSubtitle} mb-3`}>Profitto in unità e vinte/giocate di ogni motore, giornata per giornata.</p>
        {!data && !error ? <div className={`${todaySkeleton} h-48`} /> : null}
        {data ? <DailyTable data={data} /> : null}
      </section>
    </div>
  )
}
