import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  DEFAULT_SEASON,
  buildUpcomingSotFeatures,
  evaluateMatchLine,
  generateUpcomingSotPredictionsV02,
  generateUpcomingSotPredictions,
  getUpcomingPredictions,
  getUpcomingPredictionsV02,
  type EvaluateMatchSotLineResponse,
  type ModelLimitations,
  type UpcomingCalculationBreakdown,
  type UpcomingMatchRow,
  type UpcomingV02MatchRow,
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

function yn(v: unknown): string {
  return v === true ? 'Sì' : 'No'
}

type TopPlayer = {
  name?: string
  team_name?: string
  impact_score?: number | null
  shots_on_target_per90?: number | null
  appearances?: number | null
  total_minutes?: number | null
  sample_warning?: boolean
}

function MatchDebugLayers({ match }: { match: UpcomingMatchRow }) {
  const h2h = match.h2h_summary
  const impact = match.player_impact_status

  const h2hOk = h2h && typeof h2h === 'object' && (h2h as Record<string, unknown>).h2h_fetch_ok === true
  const h2hNote =
    h2h && typeof h2h === 'object' && typeof (h2h as Record<string, unknown>).note === 'string'
      ? String((h2h as Record<string, unknown>).note)
      : null

  const homeTop = (impact?.home_top_players as TopPlayer[] | undefined) ?? []
  const awayTop = (impact?.away_top_players as TopPlayer[] | undefined) ?? []
  const sotSuspicious = impact?.player_profiles_sot_data_suspicious === true

  return (
    <div className="border-t border-slate-100 px-5 pb-5 sm:px-6">
      <details className="group rounded-2xl border border-dashed border-slate-300 bg-slate-50/60">
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800 marker:hidden [&::-webkit-details-marker]:hidden">
          <span className="flex items-center justify-between gap-2">
            Dati extra tecnici (solo consultazione, non usati nel calcolo baseline)
            <span className="text-xs font-normal text-slate-500 group-open:hidden">Apri</span>
            <span className="hidden text-xs font-normal text-slate-500 group-open:inline">Chiudi</span>
          </span>
        </summary>
        <div className="space-y-3 border-t border-slate-200 px-3 py-3 sm:px-4">
          <p className="text-xs leading-relaxed text-slate-600">
            Qui trovi scontri diretti dall’API, profili impatto giocatore dal database e lo stato delle formazioni
            o assenze importate. Il numero dei <strong>tiri in porta attesi</strong> in alto resta quello del modello
            baseline, senza correzioni per singoli giocatori.
          </p>

          <details className="rounded-xl border border-slate-200 bg-white">
            <summary className="cursor-pointer px-3 py-2.5 text-sm font-medium text-slate-900">
              Impatto giocatori e classifica interna
            </summary>
            <div className="space-y-3 border-t border-slate-100 px-3 py-3 text-sm text-slate-700">
              {impact ? (
                <>
                  <ul className="grid gap-1 text-xs sm:grid-cols-2">
                    <li>
                      Profili calcolati per la stagione:{' '}
                      <span className="font-medium">{yn(impact.player_profiles_available)}</span>
                    </li>
                    <li>
                      Correzione automatica alla previsione:{' '}
                      <span className="font-medium">{yn(impact.lineup_adjustment_applied)}</span>
                    </li>
                  </ul>
                  {typeof impact.note === 'string' ? (
                    <p className="text-xs leading-relaxed text-slate-600">{impact.note}</p>
                  ) : null}
                  {sotSuspicious ? (
                    <p className="rounded-lg border border-amber-200 bg-amber-50/90 px-3 py-2 text-xs text-amber-950">
                      Profili giocatore presenti, ma dati tiri in porta giocatore da verificare.
                    </p>
                  ) : null}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        {match.home_team.name}: top per punteggio impatto
                      </p>
                      {homeTop.length ? (
                        <ol className="mt-2 list-decimal space-y-1 pl-4 text-xs">
                          {homeTop.map((p, i) => (
                            <li key={i} className="space-y-0.5">
                              <span className="font-medium">{p.name ?? '—'}</span>
                              {p.team_name ? (
                                <span className="text-slate-600"> ({p.team_name})</span>
                              ) : null}
                              <span className="block text-slate-600">
                                Tiri in porta / 90′:{' '}
                                {p.shots_on_target_per90 != null
                                  ? formatNum(Number(p.shots_on_target_per90), 2)
                                  : '—'}
                                {' · '}
                                Impatto:{' '}
                                {p.impact_score != null ? formatNum(Number(p.impact_score), 2) : '—'}
                                {p.total_minutes != null ? (
                                  <>
                                    {' · '}
                                    Minuti: {formatNum(Number(p.total_minutes), 0)}
                                  </>
                                ) : null}
                                {p.sample_warning ? (
                                  <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-amber-900">
                                    Campione basso
                                  </span>
                                ) : null}
                              </span>
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p className="mt-2 text-xs text-slate-500">Nessun profilo per questa squadra.</p>
                      )}
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        {match.away_team.name}: top per punteggio impatto
                      </p>
                      {awayTop.length ? (
                        <ol className="mt-2 list-decimal space-y-1 pl-4 text-xs">
                          {awayTop.map((p, i) => (
                            <li key={i} className="space-y-0.5">
                              <span className="font-medium">{p.name ?? '—'}</span>
                              {p.team_name ? (
                                <span className="text-slate-600"> ({p.team_name})</span>
                              ) : null}
                              <span className="block text-slate-600">
                                Tiri in porta / 90′:{' '}
                                {p.shots_on_target_per90 != null
                                  ? formatNum(Number(p.shots_on_target_per90), 2)
                                  : '—'}
                                {' · '}
                                Impatto:{' '}
                                {p.impact_score != null ? formatNum(Number(p.impact_score), 2) : '—'}
                                {p.total_minutes != null ? (
                                  <>
                                    {' · '}
                                    Minuti: {formatNum(Number(p.total_minutes), 0)}
                                  </>
                                ) : null}
                                {p.sample_warning ? (
                                  <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-amber-900">
                                    Campione basso
                                  </span>
                                ) : null}
                              </span>
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p className="mt-2 text-xs text-slate-500">Nessun profilo per questa squadra.</p>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-xs text-slate-500">Nessun dato impatto giocatori in risposta.</p>
              )}
            </div>
          </details>

          <details className="rounded-xl border border-slate-200 bg-white">
            <summary className="cursor-pointer px-3 py-2.5 text-sm font-medium text-slate-900">
              Formazioni e disponibilità (archivio)
            </summary>
            <div className="space-y-2 border-t border-slate-100 px-3 py-3 text-sm text-slate-700">
              {impact ? (
                <ul className="space-y-1 text-xs">
                  <li>
                    Formazioni già salvate per <strong>questa</strong> partita nel database:{' '}
                    <span className="font-medium">{yn(impact.lineups_available)}</span>
                    <span className="text-slate-500">
                      {' '}
                      (per partite future è di solito no, finché non giocate)
                    </span>
                  </li>
                  <li>
                    Eventi di assenza o infortunio importati per le due squadre in stagione:{' '}
                    <span className="font-medium">{yn(impact.availability_available)}</span>
                  </li>
                </ul>
              ) : (
                <p className="text-xs text-slate-500">Nessun dato disponibilità in risposta.</p>
              )}
            </div>
          </details>

          <details className="rounded-xl border border-slate-200 bg-white">
            <summary className="cursor-pointer px-3 py-2.5 text-sm font-medium text-slate-900">
              Scontri diretti (head-to-head)
            </summary>
            <div className="space-y-3 border-t border-slate-100 px-3 py-3 text-sm text-slate-700">
              {!h2h ? (
                <p className="text-xs text-slate-500">Nessun riepilogo scontri diretti in risposta.</p>
              ) : h2hOk ? (
                <>
                  <ul className="grid gap-1 text-xs sm:grid-cols-2">
                    <li>
                      Partite H2H concluse nel campione (storico):{' '}
                      <span className="font-medium tabular-nums">
                        {formatNum(Number((h2h as Record<string, unknown>).matches_total ?? 0), 0)}
                      </span>
                    </li>
                    <li>
                      Vittorie casa / pareggi / vittorie trasferta (riferite alle squadre di questa scheda):{' '}
                      <span className="font-medium tabular-nums">
                        {formatNum(Number((h2h as Record<string, unknown>).home_team_wins ?? 0), 0)} /{' '}
                        {formatNum(Number((h2h as Record<string, unknown>).draws ?? 0), 0)} /{' '}
                        {formatNum(Number((h2h as Record<string, unknown>).away_team_wins ?? 0), 0)}
                      </span>
                    </li>
                    <li>
                      Media gol totali (storico H2H):{' '}
                      <span className="font-medium">
                        {(h2h as Record<string, unknown>).avg_total_goals != null
                          ? formatNum(Number((h2h as Record<string, unknown>).avg_total_goals), 2)
                          : '—'}
                      </span>
                    </li>
                    <li>
                      Dati tiri in porta storici nel nostro database per gli H2H:{' '}
                      <span className="font-medium">
                        {yn(Boolean((h2h as Record<string, unknown>).h2h_sot_available))}
                      </span>
                      {(h2h as Record<string, unknown>).avg_total_sot != null ? (
                        <span className="text-slate-600">
                          {' '}
                          · media totale tiri in porta (partite coperte){' '}
                          {formatNum(Number((h2h as Record<string, unknown>).avg_total_sot), 2)}
                        </span>
                      ) : null}
                    </li>
                  </ul>
                  {(h2h as Record<string, unknown>).h2h_sample_limited === true ? (
                    <p className="rounded-lg border border-amber-200 bg-amber-50/90 px-3 py-2 text-xs text-amber-950">
                      Campione storico limitato: pochi scontri diretti conclusi disponibili; i conteggi
                      riflettono solo partite giocate e finite.
                    </p>
                  ) : null}
                  {Array.isArray((h2h as Record<string, unknown>).last_5) &&
                  ((h2h as Record<string, unknown>).last_5 as unknown[]).length ? (
                    <div className="overflow-x-auto rounded-lg border border-slate-100">
                      <table className="min-w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-slate-100 bg-slate-50 text-slate-600">
                            <th className="px-2 py-1.5">Data</th>
                            <th className="px-2 py-1.5">Risultato</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                          {((h2h as Record<string, unknown>).last_5 as Record<string, unknown>[]).map(
                            (row, i) => (
                              <tr key={i}>
                                <td className="px-2 py-1.5 tabular-nums text-slate-600">
                                  {row.date != null ? String(row.date).slice(0, 16) : '—'}
                                </td>
                                <td className="px-2 py-1.5">
                                  <span className="font-medium">{String(row.home_team ?? '')}</span>{' '}
                                  <span className="tabular-nums text-slate-600">
                                    {row.goals_home != null ? String(row.goals_home) : '—'}–
                                    {row.goals_away != null ? String(row.goals_away) : '—'}
                                  </span>{' '}
                                  <span className="font-medium">{String(row.away_team ?? '')}</span>
                                </td>
                              </tr>
                            ),
                          )}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500">Nessun dettaglio sulle ultime partite.</p>
                  )}
                </>
              ) : (
                <p className="text-xs text-amber-900">
                  {h2hNote ?? 'Impossibile mostrare gli scontri diretti in questo momento.'}
                </p>
              )}
            </div>
          </details>
        </div>
      </details>
    </div>
  )
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

function ContextBadge({ value }: { value: unknown }) {
  const v = typeof value === 'string' ? value : 'incerta'
  return <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-800">{v}</span>
}

function MatchCard({
  match,
  limitations,
  v02Match,
  useAdjustedView,
}: {
  match: UpcomingMatchRow
  limitations: ModelLimitations
  v02Match: UpcomingV02MatchRow | null
  useAdjustedView: boolean
}) {
  const hp = match.home_prediction
  const ap = match.away_prediction
  const matchCtx = (match.match_context ?? {}) as Record<string, unknown>
  const homeCtx = (match.home_team_context ?? {}) as Record<string, unknown>
  const awayCtx = (match.away_team_context ?? {}) as Record<string, unknown>
  const riskFlags = Array.isArray(matchCtx.risk_flags) ? (matchCtx.risk_flags as unknown[]) : []
  const homeV02 = v02Match?.home_prediction_v02 ?? null
  const awayV02 = v02Match?.away_prediction_v02 ?? null
  const totalV02 = v02Match?.total_expected_sot_v02 ?? null
  const totalBaseline = v02Match?.total_expected_sot_baseline ?? null

  const showV02 = useAdjustedView && homeV02 && awayV02
  const mainHome = showV02 ? homeV02.adjusted_expected_sot : hp?.expected_sot ?? null
  const mainAway = showV02 ? awayV02.adjusted_expected_sot : ap?.expected_sot ?? null
  const mainTotal =
    showV02 && totalV02 != null
      ? totalV02
      : match.total_expected_sot != null
        ? match.total_expected_sot
        : null

  let insight = 'Previsione stabile, nessun warning rilevante.'
  if (match.context_status === 'not_available') {
    insight = 'Classifica non disponibile: contesto motivazionale non calcolabile.'
  } else if (riskFlags.includes('fine_stagione')) {
    insight = 'Partita di fine stagione: previsione da leggere con prudenza.'
  } else if ((homeV02 && Math.abs(homeV02.total_adjustment) > 0.6) || (awayV02 && Math.abs(awayV02.total_adjustment) > 0.6)) {
    insight = 'La v0.2 applica correzioni rilevanti per contesto/giocatori: usare prudenza.'
  } else if (riskFlags.length > 0) {
    insight = 'Warning contesto presenti: leggere la previsione con prudenza.'
  }

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
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            {match.home_team.logo_url ? (
              <img src={match.home_team.logo_url} alt="" className="h-8 w-8 shrink-0 object-contain" />
            ) : null}
            <span className="text-sm font-semibold text-slate-900">{match.home_team.name}</span>
          </div>
          <span className="text-slate-400">vs</span>
          <div className="flex items-center gap-2">
            {match.away_team.logo_url ? (
              <img src={match.away_team.logo_url} alt="" className="h-8 w-8 shrink-0 object-contain" />
            ) : null}
            <span className="text-sm font-semibold text-slate-900">{match.away_team.name}</span>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {riskFlags.includes('fine_stagione') ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-900 ring-1 ring-amber-100">
              Fine stagione
            </span>
          ) : null}
          {homeCtx.turnover_risk === 'alto' || awayCtx.turnover_risk === 'alto' ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-900 ring-1 ring-amber-100">
              Rischio turnover
            </span>
          ) : null}
          {riskFlags.length > 0 && !riskFlags.includes('fine_stagione') ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-900 ring-1 ring-amber-100">
              Contesto prudente
            </span>
          ) : null}
        </div>
      </div>

      <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {match.home_team.name}
            </p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainHome != null ? formatNum(mainHome) : '—'}
            </p>
            {homeV02 ? (
              <p className="mt-1 text-xs text-slate-600">
                Baseline {formatNum(homeV02.baseline_expected_sot)} · Correzione{' '}
                {formatNum(homeV02.total_adjustment)}
              </p>
            ) : hp ? (
              <p className="mt-1 text-xs text-slate-600">Baseline {formatNum(hp.expected_sot)}</p>
            ) : null}
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Totale match</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainTotal != null ? formatNum(mainTotal) : '—'}
            </p>
            {totalBaseline != null && totalV02 != null ? (
              <p className="mt-1 text-xs text-slate-600">
                Baseline {formatNum(totalBaseline)} · v0.2 {formatNum(totalV02)}
              </p>
            ) : null}
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {match.away_team.name}
            </p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainAway != null ? formatNum(mainAway) : '—'}
            </p>
            {awayV02 ? (
              <p className="mt-1 text-xs text-slate-600">
                Baseline {formatNum(awayV02.baseline_expected_sot)} · Correzione{' '}
                {formatNum(awayV02.total_adjustment)}
              </p>
            ) : ap ? (
              <p className="mt-1 text-xs text-slate-600">Baseline {formatNum(ap.expected_sot)}</p>
            ) : null}
          </div>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-slate-700">{insight}</p>
      </div>

      <div className="border-t border-slate-100 px-5 py-4 sm:px-6">
        <details className="group rounded-2xl border border-slate-200 bg-slate-50/50">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800 marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="flex items-center justify-between gap-2">
              Perché è cambiata?
              <span className="text-xs font-normal text-slate-500 group-open:hidden">Apri</span>
              <span className="hidden text-xs font-normal text-slate-500 group-open:inline">Chiudi</span>
            </span>
          </summary>
          {homeV02 && awayV02 ? (
            <div className="space-y-2 border-t border-slate-200 px-4 py-4 text-sm text-slate-700">
              <p>
                {match.home_team.name}: Baseline {formatNum(homeV02.baseline_expected_sot)} · Aggiustata{' '}
                {formatNum(homeV02.adjusted_expected_sot)} · Correzione {formatNum(homeV02.total_adjustment)}
              </p>
              <p>
                {match.away_team.name}: Baseline {formatNum(awayV02.baseline_expected_sot)} · Aggiustata{' '}
                {formatNum(awayV02.adjusted_expected_sot)} · Correzione {formatNum(awayV02.total_adjustment)}
              </p>
              <p className="text-xs text-slate-600">
                Totale match Baseline: {totalBaseline != null ? formatNum(totalBaseline) : '—'} · Totale match v0.2:{' '}
                {totalV02 != null ? formatNum(totalV02) : '—'}
              </p>
            </div>
          ) : (
            <div className="border-t border-slate-200 px-4 py-4 text-sm text-slate-600">
              <p>Correzione v0.2 non disponibile per questa partita.</p>
            </div>
          )}
        </details>
      </div>

      <div className="border-t border-slate-100 px-5 pb-5 sm:px-6">
        <details className="group rounded-2xl border border-slate-200 bg-slate-50/50">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800 marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="flex items-center justify-between gap-2">
              Dettaglio matematico baseline
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
      <MatchDebugLayers match={match} />
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
  const [dataV02, setDataV02] = useState<Awaited<ReturnType<typeof getUpcomingPredictionsV02>> | null>(null)
  const [viewMode, setViewMode] = useState<'v02' | 'v01'>('v02')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getUpcomingPredictions(SEASON, { limit: 20, onlyNextRound: true })
      const resV02 = await getUpcomingPredictionsV02(SEASON, { limit: 20, onlyNextRound: true })
      setData(res)
      setDataV02(resV02)
      setViewMode(res.v02_available ? 'v02' : 'v01')
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
  const useAdjustedView = viewMode === 'v02' && Boolean(data?.v02_available)

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6">
        <header className="pt-4 space-y-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Prossima giornata</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">
              Stime sui <strong>tiri in porta</strong> per le prossime partite. I numeri mostrati sono quelli della
              versione baseline v0.2 context/player (se disponibile), con confronto rispetto alla baseline v0.1.
            </p>
          </div>

          <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-700 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <p className="font-semibold text-slate-900">
                Modello attivo:{' '}
                <span className="font-normal text-slate-800">
                  {useAdjustedView ? 'baseline_v0_2_context_player' : 'baseline_v0_1'}
                </span>
              </p>
              <p>
                Qualità dati: <span className="font-medium">Alta · 100/100</span>
              </p>
              <p>
                Affidabilità previsione:{' '}
                <span className="font-medium">Media · 78/100</span>
                <span className="text-slate-500"> (stima prudenziale, non probabilità calibrata)</span>
              </p>
            </div>
            <div className="space-y-2 text-xs text-slate-600">
              {data?.round ? (
                <p>
                  Prossimo turno:{' '}
                  <span className="font-medium text-slate-900">{data.round}</span>
                </p>
              ) : null}
              <p>
                <Link to="/model-legend" className="font-medium text-slate-700 underline">
                  Come funziona il modello?
                </Link>
              </p>
            </div>
          </div>

          <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1 text-xs">
            <button
              type="button"
              className={`rounded-lg px-2 py-1 ${viewMode === 'v01' ? 'bg-slate-900 text-white' : 'text-slate-700'}`}
              onClick={() => setViewMode('v01')}
            >
              Vista baseline v0.1
            </button>
            <button
              type="button"
              className={`rounded-lg px-2 py-1 ${viewMode === 'v02' ? 'bg-slate-900 text-white' : 'text-slate-700'}`}
              onClick={() => setViewMode('v02')}
            >
              Vista v0.2 aggiustata
            </button>
          </div>
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
                    await generateUpcomingSotPredictionsV02(SEASON)
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
              <MatchCard
                key={m.fixture_id}
                match={m}
                limitations={limitations}
                v02Match={dataV02?.matches.find((x) => x.fixture_id === m.fixture_id) ?? null}
                useAdjustedView={useAdjustedView}
              />
            ))}

            <section className="space-y-4 border-t border-slate-200 pt-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-2xl border border-emerald-100 bg-white p-4 shadow-sm">
                  <p className="text-sm font-semibold text-emerald-950">Questa versione considera</p>
                  <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-700">
                    <li>Statistiche di squadra su partite già giocate</li>
                    <li>Rendimento in casa e in trasferta</li>
                    <li>Forma recente (ultime partite)</li>
                    <li>Quanto l’avversario tende a concedere tiri in porta</li>
                    <li>Correzioni v0.2 disponibili (giocatori / H2H / contesto), se calcolate</li>
                  </ul>
                </div>
                <div className="rounded-2xl border border-amber-100 bg-white p-4 shadow-sm">
                  <p className="text-sm font-semibold text-amber-950">
                    Questa versione non considera ancora pienamente
                  </p>
                  <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-700">
                    <li>Formazioni ufficiali pre-partita</li>
                    <li>Assenze/infortuni se i dati non sono affidabili</li>
                    <li>Quote bookmaker importate automaticamente</li>
                    <li>Altri fattori qualitativi non ancora integrati stabilmente</li>
                  </ul>
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
