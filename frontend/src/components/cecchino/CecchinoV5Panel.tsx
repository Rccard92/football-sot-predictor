import { useEffect, useState } from 'react'
import {
  fetchV5TodayFixture,
  type V5Candidate,
  type V5FixturePlay,
  type V5FixtureView,
  type V5SpecialistView,
  type V5Status,
} from '../../lib/cecchinoV5Api'
import {
  todayBadgeActive,
  todayBadgeMuted,
  todayBadgeOk,
  todayCard,
  todayCardPadding,
  todaySectionSubtitle,
  todaySectionTitle,
} from './cecchinoTodayStyles'

const LABEL = 'text-[13px] text-slate-500'
const SIDE_LABEL = { total: 'Totale', home: 'Casa', away: 'Ospite' } as const

function pct(v: number | null | undefined): string {
  return v == null ? '–' : `${Math.round(100 * v)}%`
}

function num(v: number | null | undefined, digits = 2): string {
  return v == null ? '–' : v.toLocaleString('it-IT', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function time(iso: string | null | undefined): string {
  if (!iso) return '–'
  return new Date(iso).toLocaleString('it-IT', { timeZone: 'Europe/Rome', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function StatusBadge({ status }: { status: V5Status }) {
  return status === 'consigliata' ? (
    <span className={todayBadgeOk}>consigliato</span>
  ) : (
    <span className={todayBadgeMuted}>osservazione · non consigliato</span>
  )
}

function useV5Fixture(todayFixtureId: number) {
  const [data, setData] = useState<V5FixtureView | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    setData(null)
    setError(null)
    fetchV5TodayFixture(todayFixtureId)
      .then((d) => alive && setData(d))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      alive = false
    }
  }, [todayFixtureId])
  return { data, error, loading: !data && !error }
}

function Playable({ items, minEdge }: { items: V5Candidate[]; minEdge: number }) {
  if (!items.length) {
    return (
      <p className="text-[13px] text-slate-500">
        Nessuna linea passa la regola (probabilità prudente × quota ≥ {num(minEdge)}).
      </p>
    )
  }
  return (
    <ul className="space-y-1">
      {items.map((c, i) => (
        <li key={c.market_key} className="flex flex-wrap items-center gap-x-2 text-sm">
          {i === 0 ? <span className={todayBadgeActive}>scelta</span> : <span className="w-[52px]" />}
          <span className="font-medium text-slate-800">{c.label}</span>
          <span className={LABEL}>
            quota <b className="tabular-nums text-slate-800">{num(c.quota)}</b> {c.bookmaker} · prob. prudente {pct(c.prob_prudent)} ·
            prob. × quota {num(c.score)}
          </span>
        </li>
      ))}
    </ul>
  )
}

function StatSpecialist({ s, minEdge }: { s: V5SpecialistView; minEdge: number }) {
  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className={todaySectionTitle}>{s.label}</h3>
        <StatusBadge status={s.status} />
      </div>
      {!s.expected ? (
        <p className="text-sm text-slate-600">{s.reason ?? 'Non calcolabile per questa partita.'}</p>
      ) : (
        <>
          <p className="mb-3 text-sm text-slate-700">
            Attesi: <b className="tabular-nums">{num(s.expected.total, 1)}</b> in totale · casa{' '}
            <b className="tabular-nums">{num(s.expected.home, 1)}</b> · ospite <b className="tabular-nums">{num(s.expected.away, 1)}</b>
          </p>
          <div className="mb-3 overflow-x-auto">
            <table className="w-full min-w-[420px] text-sm">
              <thead>
                <tr className={`${LABEL} border-b border-slate-200`}>
                  <th className="px-2 py-1 text-left font-medium">Linea</th>
                  <th className="px-2 py-1 text-right font-medium">Over</th>
                  <th className="px-2 py-1 text-right font-medium">Quota</th>
                  <th className="px-2 py-1 text-right font-medium">Under</th>
                  <th className="px-2 py-1 text-right font-medium">Quota</th>
                </tr>
              </thead>
              <tbody>
                {(s.lines ?? []).map((l) => (
                  <tr key={`${l.side}-${l.line}`} className="border-b border-slate-100 last:border-0">
                    <td className="px-2 py-1 text-slate-700">
                      {SIDE_LABEL[l.side]} {num(l.line, 1)}
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums">{pct(l.p_over)}</td>
                    <td className="px-2 py-1 text-right tabular-nums text-slate-500">{num(l.quota_over)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{pct(l.p_under)}</td>
                    <td className="px-2 py-1 text-right tabular-nums text-slate-500">{num(l.quota_under)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className={`${LABEL} mb-1`}>Linee che passano la regola</div>
          <Playable items={s.playable} minEdge={minEdge} />
        </>
      )}
    </section>
  )
}

function ValoreSpecialist({ s, minEdge, band }: { s: V5SpecialistView; minEdge: number; band: [number, number] }) {
  const rows = s.markets ?? []
  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className={todaySectionTitle}>{s.label}</h3>
        <StatusBadge status={s.status} />
      </div>
      <p className={`${todaySectionSubtitle} mb-3`}>
        Probabilità gol della V4 corrette con lo storico (taratura), solo quote tra {num(band[0])} e {num(band[1])}.
      </p>
      {!rows.length ? (
        <p className="text-sm text-slate-600">{s.reason}</p>
      ) : (
        <div className="mb-3 overflow-x-auto">
          <table className="w-full min-w-[420px] text-sm">
            <thead>
              <tr className={`${LABEL} border-b border-slate-200`}>
                <th className="px-2 py-1 text-left font-medium">Mercato</th>
                <th className="px-2 py-1 text-right font-medium">Prob. V4</th>
                <th className="px-2 py-1 text-right font-medium">Prob. tarata</th>
                <th className="px-2 py-1 text-right font-medium">Quota</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.market_key} className="border-b border-slate-100 last:border-0">
                  <td className="px-2 py-1 text-slate-700">{m.label}</td>
                  <td className="px-2 py-1 text-right tabular-nums text-slate-500">{pct(m.p_model)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{pct(m.p_calibrated)}</td>
                  <td className={`px-2 py-1 text-right tabular-nums ${m.in_band ? 'font-semibold text-slate-900' : 'text-slate-400'}`}>
                    {num(m.quota)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className={`${LABEL} mb-1`}>Mercati che passano la regola</div>
      <Playable items={s.playable} minEdge={minEdge} />
    </section>
  )
}

function SealedPlays({ plays, labels }: { plays: V5FixturePlay[]; labels: Record<string, string> }) {
  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <h3 className={todaySectionTitle}>Giocate V5 in lista per questa partita</h3>
      <p className={`${todaySectionSubtitle} mb-3`}>Lista sigillata: la giocata e la sua quota non cambiano più.</p>
      {!plays.length ? (
        <p className="text-sm text-slate-500">Nessuna giocata V5 in lista per questa partita.</p>
      ) : (
        <ul className="space-y-2">
          {plays.map((p) => (
            <li key={`${p.specialist}-${p.label}`} className="text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900">{labels[p.specialist] ?? p.specialist}</span>
                <StatusBadge status={p.status} />
                <span className="text-slate-800">{p.label}</span>
                <span className="ml-auto">
                  {p.result == null ? (
                    <span className={todayBadgeActive}>aperta</span>
                  ) : p.result === 'vinta' ? (
                    <span className={todayBadgeOk}>vinta {num(p.profit_units)} u</span>
                  ) : (
                    <span className={todayBadgeMuted}>
                      {p.result} {num(p.profit_units)} u
                    </span>
                  )}
                </span>
              </div>
              <div className={LABEL}>
                quota {num(p.quota)} {p.bookmaker} (letta {time(p.taken_at)}) · prob. {pct(p.probability)}
                {p.expected != null ? ` · attesi ${num(p.expected, 1)}` : ''}
                {p.closing_quota != null ? ` · chiusura ${num(p.closing_quota)}` : ''}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function CecchinoV5Panel({ todayFixtureId }: { todayFixtureId: number }) {
  const { data, error, loading } = useV5Fixture(todayFixtureId)
  if (loading) return <div className={`${todayCard} ${todayCardPadding} h-48 animate-pulse`} aria-busy="true" />
  if (error) return <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
  if (!data || data.status !== 'ok' || !data.specialists || !data.rules) {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className={todaySectionTitle}>Cecchino V5 · specialisti</h3>
          <span className={todayBadgeMuted}>Non disponibile</span>
        </div>
        <p className="mt-2 text-sm text-slate-600">{data?.message ?? 'V5 non disponibile per questa partita.'}</p>
      </section>
    )
  }
  const rules = data.rules
  const labels = { ...(data.specialist_labels ?? {}), ...Object.fromEntries(data.specialists.map((s) => [s.key, s.label])) }
  const lh = data.fixture?.lambda_home
  const la = data.fixture?.lambda_away
  return (
    <div className="space-y-5">
      <section className={`${todayCard} ${todayCardPadding}`}>
        <h3 className={todaySectionTitle}>Cecchino V5 · specialisti</h3>
        <p className={`${todaySectionSubtitle} mt-1`}>
          Ogni specialista stima quanti tiri in porta, angoli e cartellini aspettarsi (media del campionato, forza delle squadre
          nelle ultime 30 partite, gol attesi della V4, arbitro per i cartellini) e da lì la probabilità di ogni linea, senza
          quote. Solo alla fine guarda la quota migliore tra Bet365 e Betfair: si gioca se probabilità prudente × quota ≥{' '}
          {num(rules.min_edge)}, quota tra {num(rules.stat_quota[0])} e {num(rules.stat_quota[1])}.
        </p>
        <p className={`${LABEL} mt-2`}>
          {lh != null && la != null ? `Gol attesi V4: ${num(lh)} – ${num(la)} · ` : ''}
          Quote lette: {time(data.odds_taken_at)}
          {data.fixture?.referee ? ` · Arbitro: ${data.fixture.referee}` : ''}
        </p>
      </section>

      <SealedPlays plays={data.plays ?? []} labels={labels} />

      {data.specialists.map((s) =>
        s.key === 'valore' ? (
          <ValoreSpecialist key={s.key} s={s} minEdge={rules.min_edge} band={rules.valore_quota} />
        ) : (
          <StatSpecialist key={s.key} s={s} minEdge={rules.min_edge} />
        ),
      )}
    </div>
  )
}
