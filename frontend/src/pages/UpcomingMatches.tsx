import { useCallback, useEffect, useState } from 'react'
import {
  DEFAULT_SEASON,
  buildUpcomingSotFeatures,
  evaluateMatchLine,
  generateUpcomingSotPredictions,
  getUpcomingPredictions,
  type EvaluateMatchSotLineResponse,
  type ModelLimitations,
  type UpcomingCalculationBreakdown,
  type UpcomingMatchRow,
  type UpcomingSidePrediction,
} from '../lib/api'

const SEASON = DEFAULT_SEASON

const BREAKDOWN_ROWS: {
  key:
    | 'season_avg_sot_for'
    | 'opponent_season_avg_sot_conceded'
    | 'home_away_avg_sot_for'
    | 'opponent_home_away_avg_sot_conceded'
    | 'last5_avg_sot_for'
    | 'opponent_last5_avg_sot_conceded'
  label: string
}[] = [
  { key: 'season_avg_sot_for', label: 'Media stagionale tiri in porta' },
  { key: 'opponent_season_avg_sot_conceded', label: 'Tiri concessi dall’avversario (stagione)' },
  { key: 'home_away_avg_sot_for', label: 'Media in casa o in trasferta' },
  {
    key: 'opponent_home_away_avg_sot_conceded',
    label: 'Avversario concede in casa o in trasferta',
  },
  { key: 'last5_avg_sot_for', label: 'Forma recente (ultime 5 partite)' },
  { key: 'opponent_last5_avg_sot_conceded', label: 'Avversario ultime 5 partite (concesse)' },
]

function formatKickoff(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('it-IT', { dateStyle: 'medium', timeStyle: 'short' })
}

function formatNum(n: number, maxFrac = 2): string {
  return n.toLocaleString('it-IT', { maximumFractionDigits: maxFrac, minimumFractionDigits: 0 })
}

function strengthLabel(s: EvaluateMatchSotLineResponse['strength']): string {
  const map: Record<typeof s, string> = {
    forte: 'Forte',
    interessante: 'Interessante',
    leggero: 'Leggera',
    neutro: 'Neutra',
  }
  return map[s]
}

function suggestionLabel(s: EvaluateMatchSotLineResponse['suggestion']): string {
  if (s === 'no_bet') return 'Nessuna scommessa consigliata'
  if (s === 'over') return 'Over (sopra la linea)'
  return 'Under (sotto la linea)'
}

function BreakdownTable({
  teamName,
  breakdown,
}: {
  teamName: string
  breakdown: UpcomingCalculationBreakdown | null | undefined
}) {
  if (!breakdown) {
    return (
      <p className="text-sm text-slate-500">
        Dettaglio numerico non disponibile per {teamName}: rigenera le previsioni se la partita è stata
        creata con una versione precedente del sistema.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="min-w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50/90 text-xs font-semibold uppercase tracking-wide text-slate-600">
            <th className="px-3 py-2.5">Fattore</th>
            <th className="px-3 py-2.5 text-right">Valore usato</th>
            <th className="px-3 py-2.5 text-right">Peso</th>
            <th className="px-3 py-2.5 text-right">Contributo</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {BREAKDOWN_ROWS.map(({ key, label }) => {
            const val = breakdown[key]
            const w = breakdown[`${key}_weight` as keyof UpcomingCalculationBreakdown] as number
            const c = breakdown[`${key}_contribution` as keyof UpcomingCalculationBreakdown] as number
            const fb = breakdown[`${key}_fallback_used` as keyof UpcomingCalculationBreakdown] as
              | boolean
              | undefined
            const note = breakdown[`${key}_fallback_note` as keyof UpcomingCalculationBreakdown] as
              | string
              | null
              | undefined
            return (
              <tr key={key} className="text-slate-800">
                <td className="px-3 py-2">
                  <span className="font-medium">{label}</span>
                  {fb ? (
                    <span className="mt-0.5 block text-xs font-normal text-amber-800">{note ?? 'Dato sostituito.'}</span>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{formatNum(Number(val))}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatNum(Number(w), 2)}</td>
                <td className="px-3 py-2 text-right tabular-nums font-medium">{formatNum(Number(c), 4)}</td>
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-slate-200 bg-slate-50/80 font-semibold text-slate-900">
            <td className="px-3 py-2.5" colSpan={3}>
              Tiri in porta attesi (squadra)
            </td>
            <td className="px-3 py-2.5 text-right tabular-nums">
              {formatNum(breakdown.expected_sot_total)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function TeamBox({
  team,
  pred,
}: {
  team: UpcomingMatchRow['home_team']
  pred: UpcomingSidePrediction | null
}) {
  return (
    <div className="flex flex-1 flex-col rounded-2xl border border-slate-100 bg-slate-50/40 p-4 sm:p-5">
      <div className="flex items-center gap-3">
        {team.logo_url ? (
          <img src={team.logo_url} alt="" className="h-11 w-11 shrink-0 object-contain" />
        ) : (
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-slate-200 text-xs font-bold text-slate-600">
            {team.name.slice(0, 2).toUpperCase()}
          </div>
        )}
        <p className="font-semibold text-slate-900">{team.name}</p>
      </div>
      {pred ? (
        <>
          <p className="mt-4 text-xs font-medium uppercase tracking-wide text-slate-500">
            Tiri in porta attesi
          </p>
          <p className="text-3xl font-bold tabular-nums tracking-tight text-slate-900">
            {formatNum(pred.expected_sot)}
          </p>
          <p className="mt-2 text-sm text-slate-600">
            Attacco: <span className="font-medium text-slate-800">{pred.label}</span>
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Fiducia nel dato:{' '}
            <span className="font-medium text-slate-800">
              {pred.confidence_label} (punteggio {pred.confidence_score} su 100)
            </span>
          </p>
          <p className="mt-3 text-sm leading-relaxed text-slate-700">{pred.simple_explanation}</p>
        </>
      ) : (
        <p className="mt-4 text-sm text-slate-500">Nessuna previsione disponibile per questa squadra.</p>
      )}
    </div>
  )
}

function MatchCard({ match, limitations }: { match: UpcomingMatchRow; limitations: ModelLimitations }) {
  const [bookmaker, setBookmaker] = useState('')
  const [marketType, setMarketType] = useState('match_total_sot')
  const [line, setLine] = useState('6.5')
  const [oddsStr, setOddsStr] = useState('1.50')
  const [loading, setLoading] = useState(false)
  const [evalErr, setEvalErr] = useState<string | null>(null)
  const [evalResult, setEvalResult] = useState<EvaluateMatchSotLineResponse | null>(null)

  const hp = match.home_prediction
  const ap = match.away_prediction
  const canEvaluate = Boolean(hp && ap)

  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-gradient-to-b from-slate-50/80 to-white px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {match.round ?? 'Giornata'}
          </p>
          <span className="rounded-full bg-emerald-50 px-3 py-0.5 text-xs font-medium text-emerald-800 ring-1 ring-emerald-100">
            Pre-partita
          </span>
        </div>
        <p className="mt-2 text-sm text-slate-600">{formatKickoff(match.kickoff_at)}</p>
        <h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900 sm:text-xl">
          {match.home_team.name}{' '}
          <span className="font-normal text-slate-400" aria-hidden>
            —
          </span>{' '}
          {match.away_team.name}
        </h2>
        {match.total_expected_sot != null ? (
          <p className="mt-3 text-base font-medium text-slate-800">
            Totale tiri in porta attesi (match):{' '}
            <span className="tabular-nums text-slate-900">{formatNum(match.total_expected_sot)}</span>
          </p>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            Totale match non calcolabile: servono entrambe le stime sulle due squadre.
          </p>
        )}
      </div>

      <div className="grid gap-4 p-5 sm:p-6 md:grid-cols-2">
        <TeamBox team={match.home_team} pred={hp} />
        <TeamBox team={match.away_team} pred={ap} />
      </div>

      <div className="border-t border-slate-100 px-5 py-5 sm:px-6">
        <h3 className="text-sm font-semibold text-slate-900">Valuta linea bookmaker</h3>
        <p className="mt-1 text-xs text-slate-600">
          Confronta la somma dei tiri in porta attesi con la linea che vedi sul foglio gioco. Le quote servono solo
          per una probabilità indicativa, non per cercare “valore” statistico.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-12">
          <label className="text-xs font-medium text-slate-700 lg:col-span-3">
            Bookmaker
            <input
              type="text"
              value={bookmaker}
              onChange={(e) => setBookmaker(e.target.value)}
              placeholder="es. Sisal Matchpoint"
              className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm shadow-sm outline-none ring-slate-200 focus:ring-2"
            />
          </label>
          <label className="text-xs font-medium text-slate-700 lg:col-span-4">
            Mercato
            <select
              value={marketType}
              onChange={(e) => setMarketType(e.target.value)}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm shadow-sm outline-none ring-slate-200 focus:ring-2"
            >
              <option value="match_total_sot">Totale tiri in porta (match)</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-700 lg:col-span-2">
            Linea
            <input
              type="number"
              step="0.5"
              min={0}
              max={40}
              value={line}
              onChange={(e) => setLine(e.target.value)}
              className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm tabular-nums shadow-sm outline-none ring-slate-200 focus:ring-2"
            />
          </label>
          <label className="text-xs font-medium text-slate-700 lg:col-span-2">
            Quota (opzionale)
            <input
              type="number"
              step="0.01"
              min={1.01}
              value={oddsStr}
              onChange={(e) => setOddsStr(e.target.value)}
              placeholder="es. 1.50"
              className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm tabular-nums shadow-sm outline-none ring-slate-200 focus:ring-2"
            />
          </label>
          <div className="flex items-end lg:col-span-1">
            <button
              type="button"
              disabled={loading || !canEvaluate}
              className="w-full rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={async () => {
                if (!hp || !ap) return
                setLoading(true)
                setEvalErr(null)
                setEvalResult(null)
                try {
                  const lv = Number(line)
                  if (Number.isNaN(lv)) throw new Error('Inserisci una linea numerica valida.')
                  const bm = bookmaker.trim()
                  if (!bm) throw new Error('Indica il bookmaker.')
                  let odds: number | undefined
                  const o = oddsStr.trim()
                  if (o !== '') {
                    const ov = Number(o)
                    if (Number.isNaN(ov) || ov <= 1) throw new Error('La quota deve essere maggiore di 1.')
                    odds = ov
                  }
                  const out = await evaluateMatchLine({
                    home_expected_sot: hp.expected_sot,
                    away_expected_sot: ap.expected_sot,
                    market_type: marketType,
                    line_value: lv,
                    bookmaker: bm,
                    odds,
                  })
                  setEvalResult(out)
                } catch (e) {
                  setEvalErr(e instanceof Error ? e.message : String(e))
                } finally {
                  setLoading(false)
                }
              }}
            >
              {loading ? 'Valutazione…' : 'Valuta scommessa'}
            </button>
          </div>
        </div>
        {!canEvaluate ? (
          <p className="mt-2 text-xs text-amber-800">Serve una previsione per entrambe le squadre.</p>
        ) : null}
        {evalErr ? <p className="mt-3 text-sm text-rose-700">{evalErr}</p> : null}
        {evalResult ? (
          <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-sm text-slate-800">
            <p className="text-base font-semibold text-slate-900">{evalResult.label}</p>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              <li>
                <span className="text-slate-500">Indicazione: </span>
                <span className="font-medium">{suggestionLabel(evalResult.suggestion)}</span>
              </li>
              <li>
                <span className="text-slate-500">Forza: </span>
                <span className="font-medium">{strengthLabel(evalResult.strength)}</span>
              </li>
              <li>
                <span className="text-slate-500">Tiri in porta totali attesi: </span>
                <span className="tabular-nums font-medium">{formatNum(evalResult.total_expected_sot)}</span>
              </li>
              <li>
                <span className="text-slate-500">Linea: </span>
                <span className="tabular-nums font-medium">{formatNum(evalResult.line_value)}</span>
              </li>
              <li>
                <span className="text-slate-500">Distanza dalla linea: </span>
                <span className="tabular-nums font-medium">{formatNum(evalResult.gap)}</span>
              </li>
              <li>
                <span className="text-slate-500">Bookmaker: </span>
                <span className="font-medium">{evalResult.bookmaker}</span>
              </li>
              {evalResult.odds != null ? (
                <li>
                  <span className="text-slate-500">Quota: </span>
                  <span className="tabular-nums font-medium">{formatNum(evalResult.odds, 2)}</span>
                </li>
              ) : null}
              {evalResult.implied_probability != null ? (
                <li>
                  <span className="text-slate-500">Probabilità implicita dalla quota: </span>
                  <span className="tabular-nums font-medium">
                    {formatNum(evalResult.implied_probability, 2)}%
                  </span>
                </li>
              ) : null}
            </ul>
            <p className="mt-3 text-xs leading-relaxed text-slate-600">{evalResult.explanation}</p>
          </div>
        ) : null}
      </div>

      <div className="border-t border-slate-100 px-5 pb-5 sm:px-6">
        <details className="group rounded-2xl border border-slate-200 bg-slate-50/50">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800 marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="flex items-center justify-between gap-2">
              Come è stata calcolata questa previsione?
              <span className="text-xs font-normal text-slate-500 group-open:hidden">Apri</span>
              <span className="hidden text-xs font-normal text-slate-500 group-open:inline">Chiudi</span>
            </span>
          </summary>
          <div className="space-y-6 border-t border-slate-200 px-4 py-4">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                {match.home_team.name}
              </p>
              <BreakdownTable teamName={match.home_team.name} breakdown={hp?.calculation_breakdown} />
            </div>
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                {match.away_team.name}
              </p>
              <BreakdownTable teamName={match.away_team.name} breakdown={ap?.calculation_breakdown} />
            </div>
          </div>
        </details>
      </div>

      <div className="grid gap-4 border-t border-slate-100 bg-slate-50/30 px-5 py-5 sm:grid-cols-2 sm:px-6">
        <div className="rounded-2xl border border-emerald-100 bg-white p-4 shadow-sm">
          <p className="text-sm font-semibold text-emerald-950">Cosa considera questa versione</p>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-700">
            <li>Statistiche di squadra su partite già giocate</li>
            <li>Rendimento in casa e in trasferta</li>
            <li>Forma recente (ultime partite)</li>
            <li>Quanto l’avversario tende a concedere tiri in porta</li>
          </ul>
        </div>
        <div className="rounded-2xl border border-amber-100 bg-white p-4 shadow-sm">
          <p className="text-sm font-semibold text-amber-950">Cosa non considera ancora</p>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-700">
            <li>Probabili formazioni</li>
            <li>Formazioni ufficiali</li>
            <li>Assenze e infortuni</li>
            <li>Impatto dei singoli giocatori</li>
            <li>Quote bookmaker importate automaticamente</li>
          </ul>
        </div>
      </div>
      <p className="border-t border-slate-100 px-5 py-3 text-xs leading-relaxed text-slate-500 sm:px-6">
        {limitations.note}
      </p>
    </article>
  )
}

export function UpcomingMatches() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<Awaited<ReturnType<typeof getUpcomingPredictions>> | null>(null)
  const [buildBusy, setBuildBusy] = useState(false)
  const [predBusy, setPredBusy] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getUpcomingPredictions(SEASON, { limit: 20, onlyNextRound: true })
      setData(res)
    } catch (e) {
      setData(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const hasPredictions =
    data?.matches?.some((m) => Boolean(m.home_prediction || m.away_prediction)) ?? false

  const limitations: ModelLimitations =
    data?.model_limitations ?? {
      lineups_considered: false,
      injuries_considered: false,
      odds_automatically_imported: false,
      note:
        'Questa versione baseline usa solo statistiche squadra storiche. Formazioni, assenze e quote bookmaker automatiche non sono ancora considerate.',
    }

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6">
        <header className="pt-4">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Prossima giornata</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Stime sui <strong>tiri in porta</strong> (tentativi che colpiscono lo specchio della porta) per le
            prossime partite. Puoi confrontare la somma delle due squadre con una linea del bookmaker inserita a
            mano.
          </p>
        </header>

        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="space-y-4">
            <div className="h-40 animate-pulse rounded-2xl bg-slate-200/80" />
            <div className="h-40 animate-pulse rounded-2xl bg-slate-200/80" />
          </div>
        ) : !data?.matches.length ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
            <p className="text-slate-700">Nessuna partita futura trovata nel calendario.</p>
          </div>
        ) : !hasPredictions ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-6 shadow-sm">
            <p className="font-medium text-amber-950">Genera previsioni per le prossime partite</p>
            <p className="mt-2 text-sm text-amber-900">
              Non ci sono ancora previsioni sui tiri in porta per le partite programmate. Costruisci prima le
              informazioni statistiche sulle partite future, poi genera le previsioni.
            </p>
            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                disabled={buildBusy || predBusy}
                className="rounded-2xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50 disabled:opacity-50"
                onClick={async () => {
                  setBuildBusy(true)
                  setActionMsg(null)
                  try {
                    await buildUpcomingSotFeatures(SEASON)
                    setActionMsg('Dati aggiornati per le partite future.')
                    await load()
                  } catch (e) {
                    setActionMsg(e instanceof Error ? e.message : String(e))
                  } finally {
                    setBuildBusy(false)
                  }
                }}
              >
                {buildBusy ? 'Caricamento…' : 'Costruisci dati partite future'}
              </button>
              <button
                type="button"
                disabled={buildBusy || predBusy}
                className="rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-slate-800 disabled:opacity-50"
                onClick={async () => {
                  setPredBusy(true)
                  setActionMsg(null)
                  try {
                    await generateUpcomingSotPredictions(SEASON)
                    setActionMsg('Previsioni future generate.')
                    await load()
                  } catch (e) {
                    setActionMsg(e instanceof Error ? e.message : String(e))
                  } finally {
                    setPredBusy(false)
                  }
                }}
              >
                {predBusy ? 'Caricamento…' : 'Genera previsioni future'}
              </button>
            </div>
            {actionMsg ? <p className="mt-3 text-sm text-slate-800">{actionMsg}</p> : null}
          </div>
        ) : (
          <div className="space-y-6">
            <p className="text-sm text-slate-600">
              {data.round ? (
                <>
                  <span className="font-medium text-slate-800">{data.round}</span>
                  <span className="text-slate-400"> · </span>
                </>
              ) : null}
              {data.matches_count} partite
            </p>
            {data.matches.map((m) => (
              <MatchCard key={m.fixture_id} match={m} limitations={limitations} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
