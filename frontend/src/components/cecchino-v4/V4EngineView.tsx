import type { CecchinoV4Api, V4Challenger, V4Exam, V4ExamResult } from '../../lib/cecchinoV4Api'
import { todayCard, todayCardPadding } from '../cecchino/cecchinoTodayStyles'
import {
  examOutcomeFromPassed,
  familyLabel,
  leagueName,
  V4_EXAM_OUTCOME_LABELS,
  V4_LEAGUES,
  v4Label,
  v4SectionTitle,
} from './constants'
import { fmtCount, fmtDateTimeRome, fmtDecimal, fmtTimeRome } from './format'
import { useV4Query } from './useV4Query'
import { V4ChallengerChip, V4ExamChip } from './V4Chips'
import { V4Empty, V4Error, V4Loading } from './V4States'

type Props = {
  api: CecchinoV4Api
}

const th = 'px-3 py-2 text-left text-base font-semibold uppercase tracking-wide text-slate-500'
const td = 'px-3 py-2 text-base text-slate-800'

// --- Numeri chiave da un risultato d'esame ---------------------------------------------------

const WORD_VALUES: Record<string, string> = {
  ...V4_EXAM_OUTCOME_LABELS,
  true: 'sì',
  false: 'no',
}

function formatValue(v: unknown): string {
  if (v == null) return '–'
  if (typeof v === 'boolean') return WORD_VALUES[String(v)]
  if (typeof v === 'number') {
    return Number.isInteger(v)
      ? fmtCount(v)
      : new Intl.NumberFormat('it-IT', { maximumFractionDigits: 4 }).format(v)
  }
  if (typeof v === 'string') return WORD_VALUES[v] ?? v
  if (Array.isArray(v)) return v.map(formatValue).join(', ')
  return JSON.stringify(v)
}

function humanKey(k: string): string {
  return k.replaceAll('_', ' ')
}

function flattenResult(result: V4ExamResult): Array<[string, string]> {
  const out: Array<[string, string]> = []
  for (const [k, v] of Object.entries(result)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      for (const [ck, cv] of Object.entries(v as Record<string, unknown>)) {
        out.push([`${humanKey(k)} · ${humanKey(ck)}`, formatValue(cv)])
      }
    } else {
      out.push([humanKey(k), formatValue(v)])
    }
  }
  return out
}

function KeyNumbers({ result }: { result: V4ExamResult | undefined }) {
  const rows = result ? flattenResult(result) : []
  if (rows.length === 0) return <p className="text-base text-slate-500">Nessun numero ancora.</p>
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full border-collapse">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="odd:bg-white even:bg-slate-50/60">
              <td className={`${td} text-slate-600`}>{k}</td>
              <td className={`${td} text-right font-semibold tabular-nums`}>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// --- Esami ------------------------------------------------------------------------------------

function ExamCard({ exam }: { exam: V4Exam }) {
  return (
    <article className={`${todayCard} ${todayCardPadding} space-y-3`} data-testid="v4-exam-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className={v4Label}>Esame {exam.code}</p>
          <h4 className="text-xl font-semibold text-slate-900">{exam.title}</h4>
        </div>
        <V4ExamChip outcome={examOutcomeFromPassed(exam.passed)} />
      </div>
      <p className="text-base text-slate-700">
        Pre-registrazione: <span className="font-mono text-base">{exam.preregistration}</span>
      </p>
      <p className="text-base text-slate-500">
        {exam.computed_at ? `Calcolato il ${fmtDateTimeRome(exam.computed_at)}` : 'Non ancora calcolato'}
      </p>
      <KeyNumbers result={exam.result} />
    </article>
  )
}

function ExamsSection({ api }: Props) {
  const q = useV4Query('exams', (signal) => api.getExams(signal))
  return (
    <section className="space-y-3" data-testid="v4-engine-exams">
      <h3 className={v4SectionTitle}>Esami</h3>
      <p className="text-base text-slate-600">
        Ogni esame è scritto prima dei risultati. Chi non passa non entra, nemmeno come descrizione.
      </p>
      {q.loading ? <V4Loading label="Carico gli esami…" rows={2} /> : null}
      {q.error ? <V4Error message={q.error} onRetry={q.reload} /> : null}
      {q.data && q.data.items.length === 0 ? <V4Empty title="Nessun esame registrato" /> : null}
      {q.data && q.data.items.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {q.data.items.map((e) => (
            <ExamCard key={e.code} exam={e} />
          ))}
        </div>
      ) : null}
    </section>
  )
}

// --- Arena ------------------------------------------------------------------------------------

function ChallengerRow({ c }: { c: V4Challenger }) {
  return (
    <li className={`${todayCard} ${todayCardPadding} space-y-3`} data-testid="v4-challenger">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-xl font-semibold text-slate-900">{c.name}</h4>
          {c.description ? <p className="text-base text-slate-600">{c.description}</p> : null}
        </div>
        <V4ChallengerChip status={c.status} />
      </div>
      {c.exam ? (
        <div className="space-y-2">
          <p className="text-base text-slate-500">
            {c.exam.code ? `Esame ${c.exam.code}` : 'Esame'}
            {c.exam.computed_at ? ` · calcolato il ${fmtDateTimeRome(c.exam.computed_at)}` : ' · non ancora calcolato'}
          </p>
          {c.exam.result ? <KeyNumbers result={c.exam.result} /> : null}
        </div>
      ) : null}
    </li>
  )
}

function ArenaSection({ api }: Props) {
  const q = useV4Query('challengers', (signal) => api.getChallengers(signal))
  return (
    <section className="space-y-3" data-testid="v4-engine-arena">
      <h3 className={v4SectionTitle}>Arena degli sfidanti</h3>
      <p className="text-base text-slate-600">
        Assenze, motivazione, boosting e le altre idee entrano solo se battono il campione al loro esame.
      </p>
      {q.loading ? <V4Loading label="Carico gli sfidanti…" rows={2} /> : null}
      {q.error ? <V4Error message={q.error} onRetry={q.reload} /> : null}
      {q.data && q.data.items.length === 0 ? <V4Empty title="Nessuno sfidante in arena" /> : null}
      {q.data && q.data.items.length > 0 ? (
        <ul className="grid gap-4 xl:grid-cols-2">
          {q.data.items.map((c) => (
            <ChallengerRow key={c.name} c={c} />
          ))}
        </ul>
      ) : null}
    </section>
  )
}

// --- Dati -------------------------------------------------------------------------------------

const FAMILY_ORDER = [
  'FT_1X2',
  'DOUBLE_CHANCE',
  'FT_OVER_UNDER',
  'HT_1X2',
  'AH',
  'STAT:sot',
  'STAT:shots',
  'STAT:corners',
  'STAT:cards',
  'STAT:fouls',
]

function DataSection({ api }: Props) {
  const q = useV4Query('engine-data', (signal) => api.getEngineData(signal))

  let body = null
  if (q.loading) body = <V4Loading label="Carico i dati…" rows={2} />
  else if (q.error) body = <V4Error message={q.error} onRetry={q.reload} />
  else if (q.data) {
    const data = q.data
    const familySet = new Set<string>()
    for (const row of data.coverage) for (const k of Object.keys(row.markets)) familySet.add(k)
    const families = [...familySet].sort((a, b) => {
      const ia = FAMILY_ORDER.indexOf(a)
      const ib = FAMILY_ORDER.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b)
    })
    const coverageByLeague = new Map(data.coverage.map((r) => [r.league_code, r]))
    const leagueOrder = V4_LEAGUES.map((l) => l.code).filter((c) => coverageByLeague.has(c))
    for (const r of data.coverage) if (!leagueOrder.includes(r.league_code)) leagueOrder.push(r.league_code)
    const budgetPct = data.api_budget.stop_at > 0 ? Math.min(100, (data.api_budget.calls / data.api_budget.stop_at) * 100) : 0

    body = (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className={`${todayCard} ${todayCardPadding} space-y-2`}>
            <p className={v4Label}>Budget API-Football</p>
            <p className="text-2xl font-bold tabular-nums text-slate-900" data-testid="v4-api-budget">
              {fmtCount(data.api_budget.calls)} / {fmtCount(data.api_budget.stop_at)} chiamate oggi
            </p>
            <div className="h-2 overflow-hidden rounded-full bg-slate-200" aria-hidden>
              <div
                className={`h-full rounded-full ${budgetPct > 80 ? 'bg-red-500' : budgetPct > 50 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                style={{ width: `${budgetPct}%` }}
              />
            </div>
            <p className="text-base text-slate-500">La V4 si ferma da sola alla soglia, per non lasciare Cecchino Today senza quota.</p>
          </div>
          <div className={`${todayCard} ${todayCardPadding} space-y-2`}>
            <p className={v4Label}>Registro quote Bet365 e Betfair</p>
            <p className="text-2xl font-bold tabular-nums text-slate-900">
              {fmtCount(data.odds_registry.snapshots_today)} istantanee oggi
            </p>
            <p className="text-base text-slate-500">
              {data.odds_registry.last_taken_at
                ? `Ultima presa alle ${fmtTimeRome(data.odds_registry.last_taken_at)}`
                : 'Nessuna istantanea ancora oggi'}
            </p>
          </div>
        </div>

        <div className={`${todayCard} ${todayCardPadding} space-y-3`}>
          <h4 className="text-xl font-semibold text-slate-900">Copertura dei mercati per divisione</h4>
          {families.length === 0 ? (
            <p className="text-base text-slate-500">Copertura non ancora misurata.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full border-collapse" data-testid="v4-coverage-table">
                <thead className="bg-slate-50">
                  <tr>
                    <th scope="col" className={th}>Campionato</th>
                    {families.map((f) => (
                      <th key={f} scope="col" className={`${th} text-center`}>
                        {familyLabel(f)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {leagueOrder.map((code) => {
                    const row = coverageByLeague.get(code)
                    return (
                      <tr key={code} className="odd:bg-white even:bg-slate-50/60">
                        <td className={`${td} font-medium text-slate-900`}>{leagueName(code)}</td>
                        {families.map((f) => {
                          const ok = row?.markets[f] === true
                          return (
                            <td
                              key={f}
                              className={`${td} text-center text-xl ${ok ? 'text-emerald-600' : 'text-slate-300'}`}
                              aria-label={ok ? 'quotato' : 'non quotato'}
                            >
                              {ok ? '✓' : '–'}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className={`${todayCard} ${todayCardPadding} space-y-3`}>
          <h4 className="text-xl font-semibold text-slate-900">Qualità dei dati per campionato</h4>
          {data.quality.length === 0 ? (
            <p className="text-base text-slate-500">Nessuna partita ancora in archivio.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full border-collapse" data-testid="v4-quality-table">
                <thead className="bg-slate-50">
                  <tr>
                    <th scope="col" className={th}>Campionato</th>
                    <th scope="col" className={`${th} text-right`}>Partite</th>
                    <th scope="col" className={`${th} text-right`}>Senza statistiche</th>
                    <th scope="col" className={`${th} text-right`}>Senza formazioni</th>
                    <th scope="col" className={`${th} text-right`}>Senza quote</th>
                  </tr>
                </thead>
                <tbody>
                  {data.quality.map((r) => (
                    <tr key={r.league_code} className="odd:bg-white even:bg-slate-50/60">
                      <td className={`${td} font-medium text-slate-900`}>{leagueName(r.league_code)}</td>
                      <td className={`${td} text-right tabular-nums`}>{fmtCount(r.fixtures)}</td>
                      <td className={`${td} text-right tabular-nums`}>{fmtDecimal(r.missing_stats_pct, 1)}%</td>
                      <td className={`${td} text-right tabular-nums`}>{fmtDecimal(r.missing_lineups_pct, 1)}%</td>
                      <td className={`${td} text-right tabular-nums`}>{fmtDecimal(r.missing_odds_pct, 1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <section className="space-y-3" data-testid="v4-engine-data">
      <h3 className={v4SectionTitle}>Dati</h3>
      {body}
    </section>
  )
}

export function V4EngineView({ api }: Props) {
  return (
    <div className="space-y-8" data-testid="v4-engine">
      <ExamsSection api={api} />
      <ArenaSection api={api} />
      <DataSection api={api} />
    </div>
  )
}
