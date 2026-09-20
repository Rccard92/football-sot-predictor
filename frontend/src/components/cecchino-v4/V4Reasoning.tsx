import type {
  V4AftermathBlock,
  V4ContextBlock,
  V4FixtureCard,
  V4FixtureDetail,
  V4FormSide,
  V4WhoTeam,
  V4WhyBlock,
} from '../../lib/cecchinoV4Api'
import { todayBadgeMuted, todayBadgeOk, todayCard, todayCardPadding } from '../cecchino/cecchinoTodayStyles'
import {
  noPlayReasonLabel,
  V4_BLOCK_TITLES,
  V4_LINEUPS_LABELS,
  V4_PLAY_RESULT_CHIP,
  V4_PLAY_RESULT_LABELS,
  V4_TREND_ARROW,
  V4_UNCERTAINTY_LABELS,
  v4Chip,
  v4Label,
  v4Mono,
} from './constants'
import { capitalize, fmtDateTimeRome, fmtDecimal, fmtOrdinal, fmtPct, fmtScore, fmtSigned } from './format'
import { V4PlayLine } from './V4FixtureCard'
import { V4HowBars } from './V4HowBars'
import { V4MarketsTable } from './V4MarketsTable'
import { V4ReasoningBlock } from './V4ReasoningBlock'
import { V4ScoreMatrix } from './V4ScoreMatrix'

type Props = {
  detail: V4FixtureDetail
}

// --- Intestazione (come CecchinoTodayDetailHeader) -----------------------------------------

function Header({ fixture }: { fixture: V4FixtureCard }) {
  const uncertainty = fixture.uncertainty
  return (
    <header className={`${todayCard} ${todayCardPadding}`} data-testid="v4-reasoning-header">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            {fixture.competition} · {fixture.season_label}
          </p>
          <h3 className="mt-1 text-xl font-bold text-slate-900">
            {fixture.home_team} - {fixture.away_team}
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            Calcio d&apos;inizio <span className={`${v4Mono} font-medium text-slate-800`}>{fmtDateTimeRome(fixture.kickoff_at)}</span>
            {fixture.result ? (
              <>
                {' '}
                · finita <span className={`${v4Mono} font-semibold text-slate-800`}>{fmtScore(fixture.result.ft_home, fixture.result.ft_away)}</span>
              </>
            ) : null}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={fixture.lineups_status === 'ufficiali' ? todayBadgeOk : todayBadgeMuted}>
            {V4_LINEUPS_LABELS[fixture.lineups_status]}
          </span>
          {uncertainty ? (
            <span className={uncertainty.level === 'bassa' ? todayBadgeOk : todayBadgeMuted}>
              {V4_UNCERTAINTY_LABELS[uncertainty.level]}
            </span>
          ) : null}
        </div>
      </div>
    </header>
  )
}

// --- Blocco 1: piccola griglia di definizioni ------------------------------------------------

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className={v4Label}>{label}</p>
      <p className={`${v4Mono} text-sm font-semibold text-slate-900`}>{value}</p>
    </div>
  )
}

function TeamWho({ name, team }: { name: string; team: V4WhoTeam }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-3">
      <p className="text-sm font-semibold text-slate-900">
        {name}
        {team.trend ? (
          <span className="ml-2 text-xs font-normal text-slate-500" title={`Tendenza ${team.trend}`}>
            {V4_TREND_ARROW[team.trend] ?? ''} {team.trend}
          </span>
        ) : null}
      </p>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2">
        <Stat label="Attacco" value={`${fmtOrdinal(team.attack_rank)} su ${team.teams_in_division} (${fmtSigned(team.attack)})`} />
        <Stat label="Difesa" value={`${fmtOrdinal(team.defence_rank)} su ${team.teams_in_division} (${fmtSigned(team.defence)})`} />
        <Stat label="Conoscenza" value={`${team.known} · ${fmtDecimal(team.evidence, 0)} partite eq.`} />
        {team.home_advantage != null ? <Stat label="Vantaggio casa" value={fmtSigned(team.home_advantage)} /> : null}
      </div>
      {team.inherited ? <p className="mt-2 text-xs text-slate-500">{team.inherited}</p> : null}
    </div>
  )
}

// --- Blocco 3 -------------------------------------------------------------------------------

function describeDelta(delta: number | null, unit: string): string | null {
  if (delta == null) return null
  if (delta > 0.05) return `sopra l'atteso di ${fmtDecimal(delta, 1)} ${unit} a partita`
  if (delta < -0.05) return `sotto l'atteso di ${fmtDecimal(Math.abs(delta), 1)} ${unit} a partita`
  return `in linea con l'atteso nei ${unit}`
}

function formLine(team: string, side: V4FormSide | null): string | null {
  if (!side) return null
  const parts = [describeDelta(side.goals_delta, 'gol'), describeDelta(side.shots_delta, 'tiri')].filter(
    (s): s is string => s != null,
  )
  if (parts.length === 0) return null
  return `${team}: nelle ultime ${side.matches} partite ${parts.join(', ')}`
}

function contextLines(ctx: V4ContextBlock, home: string, away: string): string[] {
  const out: string[] = []
  if (ctx.form) {
    for (const line of [formLine(home, ctx.form.home), formLine(away, ctx.form.away)]) {
      if (line) out.push(line)
    }
  }
  if (ctx.rest && (ctx.rest.home_days != null || ctx.rest.away_days != null)) {
    const sides = []
    if (ctx.rest.home_days != null) sides.push(`${home} ${ctx.rest.home_days} giorni`)
    if (ctx.rest.away_days != null) sides.push(`${away} ${ctx.rest.away_days} giorni`)
    out.push(`Riposo: ${sides.join(', ')}${ctx.rest.final_phase ? ' · fase finale della stagione' : ''}`)
  }
  if (ctx.motivation && (ctx.motivation.home || ctx.motivation.away)) {
    const sides = []
    if (ctx.motivation.home) sides.push(`${home}: ${ctx.motivation.home}`)
    if (ctx.motivation.away) sides.push(`${away}: ${ctx.motivation.away}`)
    out.push(`Motivazione. ${sides.join('. ')}`)
  }
  if (ctx.lineups) {
    out.push(V4_LINEUPS_LABELS[ctx.lineups.status])
    if (ctx.lineups.absences.length > 0) {
      const list = ctx.lineups.absences
        .map((a) => {
          const team = a.team === 'home' ? home : away
          const bits = [team, a.role, a.impact != null ? `impatto ${fmtSigned(a.impact)} gol` : null].filter(Boolean)
          return `${a.player} (${bits.join(', ')})`
        })
        .join('; ')
      out.push(`Assenze: ${list}`)
    }
  }
  if (ctx.referee) {
    out.push(
      `Arbitro: ${ctx.referee.name}${
        ctx.referee.cards_per_match != null ? ` · ${fmtDecimal(ctx.referee.cards_per_match, 1)} cartellini a partita` : ''
      }`,
    )
  }
  return out
}

// --- Blocco 5 e 6 -------------------------------------------------------------------------------

function WhyBody({ why }: { why: V4WhyBlock }) {
  return (
    <div className="space-y-3">
      {why.play ? (
        <div data-testid="v4-why-play">
          <V4PlayLine play={why.play} align="left" />
        </div>
      ) : (
        <p className="text-sm font-medium text-slate-600" data-testid="v4-why-no-play">
          Nessuna giocata · {noPlayReasonLabel(why.reason)}
        </p>
      )}
      <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-800">
        {why.sentences.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ul>
      {why.would_change.length > 0 ? (
        <div>
          <p className={v4Label}>Cosa la farebbe cambiare</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {why.would_change.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

function AftermathBody({ aftermath, home, away }: { aftermath: V4AftermathBlock; home: string; away: string }) {
  const th = 'px-2 py-1.5 text-left text-xs font-medium text-slate-500'
  const td = 'px-2 py-1.5 text-sm text-slate-800'
  const numCell = `${td} ${v4Mono} text-right`
  const actual = (v: number | null) => (v == null ? '–' : String(v))
  const rows: Array<{ key: string; label: string; expected: number | null; actual: number | null }> = [
    { key: 'goals-home', label: `Gol ${home}`, expected: aftermath.goals.expected_home, actual: aftermath.goals.actual_home },
    { key: 'goals-away', label: `Gol ${away}`, expected: aftermath.goals.expected_away, actual: aftermath.goals.actual_away },
  ]
  for (const s of aftermath.stats) {
    rows.push({ key: `${s.stat}-home`, label: `${capitalize(s.label)} ${home}`, expected: s.expected_home, actual: s.actual_home })
    rows.push({ key: `${s.stat}-away`, label: `${capitalize(s.label)} ${away}`, expected: s.expected_away, actual: s.actual_away })
  }
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full border-collapse">
          <thead className="bg-slate-50">
            <tr>
              <th scope="col" className={th}>Cosa</th>
              <th scope="col" className={`${th} text-right`}>Previsto</th>
              <th scope="col" className={`${th} text-right`}>Reale</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="odd:bg-white even:bg-slate-50/60">
                <td className={td}>{r.label}</td>
                <td className={numCell}>{fmtDecimal(r.expected, 1)}</td>
                <td className={`${numCell} font-semibold`}>{actual(r.actual)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {aftermath.play ? (
        <p className="flex flex-wrap items-center gap-2 text-sm text-slate-800">
          Giocata {aftermath.play.label}
          {aftermath.play.outcome ? (
            <span className={`${v4Chip} ${V4_PLAY_RESULT_CHIP[aftermath.play.outcome]}`}>
              {V4_PLAY_RESULT_LABELS[aftermath.play.outcome]}
            </span>
          ) : null}
          {aftermath.play.profit_units != null ? (
            <span className={`${v4Mono} text-xs text-slate-500`}>
              ({fmtSigned(aftermath.play.profit_units, 2)} unità a puntata piatta)
            </span>
          ) : null}
        </p>
      ) : null}
      {aftermath.luck ? <p className="text-sm text-slate-700">{aftermath.luck}</p> : null}
    </div>
  )
}

// --- Il Ragionamento -------------------------------------------------------------------------------

/**
 * Sei blocchi. Aperti all'avvio: "Perché sì, perché no" (la risposta) in testa e "Chi sono";
 * gli altri chiusi, si aprono a richiesta.
 */
export function V4Reasoning({ detail }: Props) {
  const { fixture, blocks } = detail
  const home = fixture.home_team
  const away = fixture.away_team
  const ctxLines = blocks.context ? contextLines(blocks.context, home, away) : []
  const showContext = blocks.context != null && (ctxLines.length > 0 || Boolean(blocks.context.sentence))

  return (
    <div className="space-y-3" data-testid="v4-reasoning">
      <Header fixture={fixture} />

      {blocks.why ? (
        <V4ReasoningBlock index={5} title={V4_BLOCK_TITLES[4]} defaultOpen>
          <WhyBody why={blocks.why} />
        </V4ReasoningBlock>
      ) : null}

      {blocks.who ? (
        <V4ReasoningBlock index={1} title={V4_BLOCK_TITLES[0]} sentence={blocks.who.sentence} defaultOpen>
          <div className="grid gap-3 sm:grid-cols-2">
            <TeamWho name={home} team={blocks.who.home} />
            <TeamWho name={away} team={blocks.who.away} />
          </div>
        </V4ReasoningBlock>
      ) : null}

      {blocks.how && blocks.how.rows.length > 0 ? (
        <V4ReasoningBlock index={2} title={V4_BLOCK_TITLES[1]} sentence={blocks.how.sentence}>
          <V4HowBars rows={blocks.how.rows} homeTeam={home} awayTeam={away} />
        </V4ReasoningBlock>
      ) : null}

      {showContext && blocks.context ? (
        <V4ReasoningBlock index={3} title={V4_BLOCK_TITLES[2]} sentence={blocks.context.sentence}>
          {ctxLines.length > 0 ? (
            <ul className="space-y-1 text-sm text-slate-800">
              {ctxLines.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          ) : null}
        </V4ReasoningBlock>
      ) : null}

      {blocks.predicts ? (
        <V4ReasoningBlock index={4} title={V4_BLOCK_TITLES[3]} sentence={blocks.predicts.sentence}>
          <V4MarketsTable
            markets={blocks.predicts.markets}
            homeTeam={home}
            awayTeam={away}
            bestKey={fixture.best_play?.market_key ?? null}
          />
          {blocks.predicts.most_likely_score ? (
            <p className="text-sm text-slate-700">
              Risultato più probabile{' '}
              <span className={`${v4Mono} font-semibold`}>
                {fmtScore(blocks.predicts.most_likely_score.home, blocks.predicts.most_likely_score.away)}
              </span>{' '}
              al <span className={v4Mono}>{fmtPct(blocks.predicts.most_likely_score.p)}</span>
            </p>
          ) : null}
          {blocks.predicts.score_matrix.length > 0 ? (
            <V4ScoreMatrix
              matrix={blocks.predicts.score_matrix}
              maxGoals={blocks.predicts.max_goals}
              homeTeam={home}
              awayTeam={away}
            />
          ) : null}
        </V4ReasoningBlock>
      ) : null}

      {blocks.aftermath ? (
        <V4ReasoningBlock index={6} title={V4_BLOCK_TITLES[5]} sentence={blocks.aftermath.sentence}>
          <AftermathBody aftermath={blocks.aftermath} home={home} away={away} />
        </V4ReasoningBlock>
      ) : null}
    </div>
  )
}
