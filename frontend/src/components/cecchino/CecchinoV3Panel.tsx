import type { LiveModelPrediction, V3IndexBlock } from '../../lib/cecchinoLiveApi'
import { CecchinoPatternHero } from './CecchinoPatternHero'
import { CecchinoPurchasabilityIndexV25 } from './CecchinoPurchasabilityIndexV25'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'
import { Badge, KpiPanel, PatternPanel, SourceBadge, Stat, useLiveFixture } from './CecchinoV25Panel'

/** Scheda V3 estesa in Cecchino Today: stessi blocchi e stessa grafica di V2 e V2.5. */

const INDEX_CLASS: Record<string, string> = {
  molto_basso: 'Molto basso',
  basso: 'Basso',
  medio: 'Medio',
  alto: 'Alto',
  molto_alto: 'Molto alto',
}

const UNAVAILABLE_REASON: Record<string, string> = {
  no_statistics:
    "API-Football non fornisce tiri e tiri in porta per questo campionato (o non ancora abbastanza partite): la V3 usa questi dati e qui non si può calcolare.",
  no_competition: 'Partita non collegata a un campionato nel database.',
  no_fixture: 'Partita non collegata allo storico.',
  not_upcoming: 'La partita è già iniziata o finita.',
  not_computable: 'Storico insufficiente per calcolare la V3.',
}

function num(v: number | null | undefined, d = 2): string {
  return v == null ? '—' : v.toLocaleString('it-IT', { maximumFractionDigits: d, minimumFractionDigits: d })
}

function pct(v: number | null | undefined, d = 1): string {
  return v == null ? '—' : `${(v * 100).toLocaleString('it-IT', { maximumFractionDigits: d, minimumFractionDigits: d })}%`
}

function signed(v: number | null | undefined, d = 1, suffix = ''): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toLocaleString('it-IT', { maximumFractionDigits: d, minimumFractionDigits: d })}${suffix}`
}

function indexClass(block: V3IndexBlock | undefined): string {
  return block?.class ? (INDEX_CLASS[block.class] ?? block.class) : 'Serve più storico'
}

// ---------------------------------------------------------------------------

function SpecialistsPanel({ p }: { p: LiveModelPrediction }) {
  const s = p.modules?.specialists ?? {}
  const w = s.weights ?? {}
  const xg = p.modules?.expected_goals
  const form = s.form ?? {}
  const cal = s.calendar
  const rows: { name: string; hint: string; home: number | null | undefined; away: number | null | undefined; weight: number | undefined; extra?: string }[] = [
    { name: 'Forza', hint: 'Attacco e difesa stimati sui gol', home: s.forza?.home, away: s.forza?.away, weight: w.forza },
    {
      name: 'Gioco · tiri in porta',
      hint: 'Tiri in porta attesi tradotti in gol',
      home: s.sot?.home,
      away: s.sot?.away,
      weight: w.sot,
      extra: s.sot ? `volume ${num(s.sot.volume_home, 1)} – ${num(s.sot.volume_away, 1)}` : undefined,
    },
    {
      name: 'Gioco · tiri',
      hint: 'Tiri attesi tradotti in gol',
      home: s.shots?.home,
      away: s.shots?.away,
      weight: w.shots,
      extra: s.shots ? `volume ${num(s.shots.volume_home, 1)} – ${num(s.shots.volume_away, 1)}` : undefined,
    },
  ]
  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <h3 className={todaySectionTitle}>Specialisti V3</h3>
      <p className={todaySectionSubtitle}>
        Ogni specialista stima i gol attesi a modo suo; l&apos;orchestratore li combina con i pesi fissati sull&apos;ultima stagione del Lab.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
              <th className="py-2 pr-2 font-medium">Specialista</th>
              <th className="py-2 pr-2 text-right font-medium">Gol attesi casa</th>
              <th className="py-2 pr-2 text-right font-medium">Gol attesi ospite</th>
              <th className="py-2 text-right font-medium">Peso</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-b border-slate-100 align-top">
                <td className="py-2 pr-2">
                  <div className="font-medium text-slate-900">{r.name}</div>
                  <div className="text-[11px] text-slate-500">
                    {r.hint}
                    {r.extra ? ` · ${r.extra}` : ''}
                  </div>
                </td>
                <td className="py-2 pr-2 text-right tabular-nums">{num(r.home)}</td>
                <td className="py-2 pr-2 text-right tabular-nums">{num(r.away)}</td>
                <td className="py-2 text-right tabular-nums text-slate-600">{num(r.weight, 2)}</td>
              </tr>
            ))}
            <tr className="bg-slate-50 font-semibold">
              <td className="py-2 pr-2 text-slate-900">Gol attesi V3 (con forma e calendario)</td>
              <td className="py-2 pr-2 text-right tabular-nums">{num(xg?.home)}</td>
              <td className="py-2 pr-2 text-right tabular-nums">{num(xg?.away)}</td>
              <td className="py-2 text-right" />
            </tr>
          </tbody>
        </table>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-3 sm:grid-cols-4">
        <Stat label="Forma casa (tiri)" value={signed(form.shots_home as number | null | undefined, 2)} />
        <Stat label="Forma ospite (tiri)" value={signed(form.shots_away as number | null | undefined, 2)} />
        <Stat label="Riposo casa / ospite" value={cal ? `${cal.rest_days_home ?? '—'} / ${cal.rest_days_away ?? '—'} gg` : '—'} />
        <Stat label="Fase finale" value={cal ? (cal.final_phase ? 'Sì' : 'No') : '—'} />
      </div>
      <p className="mt-2 text-[11px] text-slate-500">Forma: 0 = in linea con le attese, positivo = sopra le attese nelle ultime 5 partite.</p>
    </section>
  )
}

function IndexCard({ number, title, question, value, valueLabel, block, reading }: {
  number: number
  title: string
  question: string
  value: string
  valueLabel: string
  block: V3IndexBlock | undefined
  reading: string
}) {
  return (
    <article className={`${todayCard} ${todayCardPadding} flex flex-col gap-3`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Indice {number}</p>
          <h4 className="text-sm font-semibold text-slate-900">{title}</h4>
        </div>
        <span className="inline-flex shrink-0 items-center rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">V3</span>
      </div>
      <p className="text-xs text-slate-500">{question}</p>
      <div className="flex items-end justify-between gap-3 border-t border-slate-100 pt-3">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-slate-400">{valueLabel}</p>
          <p className="text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-wide text-slate-400">Classe</p>
          <p className="text-sm font-medium text-slate-800">{indexClass(block)}</p>
          {block?.percentile != null && <p className="mt-0.5 text-xs text-slate-500">percentile {num(block.percentile, 0)}</p>}
        </div>
      </div>
      <p className="text-xs leading-relaxed text-slate-700">{reading}</p>
    </article>
  )
}

function IndicesPanel({ p }: { p: LiveModelPrediction }) {
  const idx = p.modules?.indices ?? {}
  const eq = idx.equilibrio
  const dr = idx.pareggio
  const gi = idx.intensita_goal
  const fav = eq?.favourite === 'home' ? 'la squadra di casa' : eq?.favourite === 'away' ? "l'ospite" : 'nessuna delle due'
  const formHome = idx.forma?.home
  const formAway = idx.forma?.away
  return (
    <section className="space-y-4">
      <div>
        <h3 className={todaySectionTitle}>Indici V3</h3>
        <p className={`mt-1 ${todaySectionSubtitle}`}>Letture della partita dagli agenti V3, senza quote del book.</p>
        <p className="mt-1 text-xs text-slate-500">
          Classi = posizione della partita tra quelle già giocate nello stesso campionato (servono almeno 200 partite).
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <IndexCard
          number={1}
          title="Equilibrio"
          question="Quanto sono vicine le probabilità di 1 e di 2?"
          valueLabel="Indice equilibrio (100 = alla pari)"
          value={num(eq?.value, 1)}
          block={eq}
          reading={`Favorita: ${fav}, distanza tra 1 e 2 di ${num(eq?.gap_pp, 1)} punti.`}
        />
        <IndexCard
          number={2}
          title="Pareggio"
          question="Quanto è probabile la X rispetto al campionato?"
          valueLabel="Probabilità X"
          value={pct(dr?.prob)}
          block={dr}
          reading={
            dr?.league_draw_rate != null
              ? `Nel campionato finisce in pareggio il ${pct(dr.league_draw_rate)} delle partite (${signed(dr.delta_pp, 1, ' pt')} per questa).`
              : 'Media pareggi del campionato non ancora disponibile.'
          }
        />
        <IndexCard
          number={3}
          title="Intensità goal"
          question="Quanti gol ci si aspetta rispetto al campionato?"
          valueLabel="Gol attesi totali"
          value={num(gi?.total, 2)}
          block={gi}
          reading={
            gi?.league_goals_avg != null
              ? `Media del campionato ${num(gi.league_goals_avg, 2)} gol (rapporto ${num(gi.ratio, 2)}). Over 2.5 al ${pct(gi.p_over_2_5)}.`
              : `Over 2.5 al ${pct(gi?.p_over_2_5)}.`
          }
        />
        <article className={`${todayCard} ${todayCardPadding} flex flex-col gap-3`}>
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Indice 4</p>
              <h4 className="text-sm font-semibold text-slate-900">Forma</h4>
            </div>
            <span className="inline-flex shrink-0 items-center rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">V3</span>
          </div>
          <p className="text-xs text-slate-500">Nelle ultime 5 partite le squadre hanno fatto meglio o peggio delle attese?</p>
          <div className="grid grid-cols-2 gap-3 border-t border-slate-100 pt-3 text-sm">
            {[
              ['Casa', formHome],
              ['Ospite', formAway],
            ].map(([label, f]) => {
              const block = f as { gioco: number; risultati: number; matches: number | null } | null | undefined
              return (
                <div key={label as string}>
                  <p className="text-[10px] uppercase tracking-wide text-slate-400">{label as string}</p>
                  <p className="font-semibold tabular-nums text-slate-900">Gioco {signed(block?.gioco, 2)}</p>
                  <p className="tabular-nums text-slate-700">Risultati {signed(block?.risultati, 2)}</p>
                </div>
              )
            })}
          </div>
          <p className="text-xs leading-relaxed text-slate-700">
            Positivo = sopra le attese (crea più tiri o fa più gol di quanto previsto, al netto degli avversari affrontati).
          </p>
        </article>
      </div>
    </section>
  )
}

export function CecchinoV3Panel({ todayFixtureId }: { todayFixtureId: number }) {
  const { data, error, loading } = useLiveFixture(todayFixtureId)
  if (loading) return <div className={`${todayCard} ${todayCardPadding} h-48 animate-pulse`} aria-busy="true" />
  if (error) return <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
  const p = data?.models['V3']
  if (!p || p.status === 'error' || p.status === 'unavailable' || !p.markets) {
    const h = p?.history
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className={todaySectionTitle}>Cecchino V3 estesa</h3>
          <Badge>Non disponibile</Badge>
        </div>
        <p className="mt-2 text-sm text-slate-600">
          {p?.error ? `Errore di calcolo: ${p.error}` : (UNAVAILABLE_REASON[p?.reason ?? ''] ?? 'V3 non calcolabile per questa partita.')}
        </p>
        {h && (
          <p className="mt-2 text-xs text-slate-500">
            Stagione in corso: {h.matches_current_season ?? 0} partite, di cui {h.matches_with_statistics ?? 0} con tiri e tiri in porta.
          </p>
        )}
      </section>
    )
  }
  const h = p.modules?.history
  const played = p.modules?.played
  return (
    <div className="space-y-5">
      <section className={`${todayCard} ${todayCardPadding}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className={todaySectionTitle}>Cecchino V3 estesa</h3>
            <p className={todaySectionSubtitle}>
              Modello V3 del Lab (parametri congelati) su dati API-Football · stagione {h?.matches_current_season ?? '—'} partite, precedente{' '}
              {h?.matches_previous_season ?? '—'}, con statistiche {h?.matches_with_statistics ?? '—'}
            </p>
          </div>
          <SourceBadge p={p} />
        </div>
        {!p.eligible && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Inizio stagione: servono almeno 5 partite giocate per squadra (casa {played?.home ?? '—'}, ospite {played?.away ?? '—'}). Numeri indicativi.
          </p>
        )}
      </section>
      <CecchinoPurchasabilityIndexV25 p={p} model="V3" />
      <CecchinoPatternHero p={p} model="V3" hideWhenEmpty />
      <KpiPanel p={p} title="PANNELLO KPI V3" showPurchasability={false} />
      <SpecialistsPanel p={p} />
      <IndicesPanel p={p} />
      <PatternPanel p={p} title="Pattern Master V3 senza quota" model="V3" />
      <p className="text-[11px] text-slate-500">
        Pattern V3 con la condizione &quot;livello&quot; (campionati top o minori del Lab) non sono verificabili sui campionati API-Football e restano spenti.
      </p>
    </div>
  )
}
