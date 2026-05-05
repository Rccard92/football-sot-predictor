import type { UpcomingMatchRow } from '../../lib/api'
import { formatNum, yn } from './format'
import type { TopPlayer } from './types'

export function MatchDebugLayers({ match }: { match: UpcomingMatchRow }) {
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
            Qui trovi scontri diretti dall’API, profili impatto giocatore dal database e lo stato delle formazioni o
            assenze importate. Il numero dei <strong>tiri in porta attesi</strong> in alto resta quello del modello
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
                              {p.team_name ? <span className="text-slate-600"> ({p.team_name})</span> : null}
                              <span className="block text-slate-600">
                                Tiri in porta / 90′:{' '}
                                {p.shots_on_target_per90 != null ? formatNum(Number(p.shots_on_target_per90), 2) : '—'}
                                {' · '}
                                Impatto: {p.impact_score != null ? formatNum(Number(p.impact_score), 2) : '—'}
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
                              {p.team_name ? <span className="text-slate-600"> ({p.team_name})</span> : null}
                              <span className="block text-slate-600">
                                Tiri in porta / 90′:{' '}
                                {p.shots_on_target_per90 != null ? formatNum(Number(p.shots_on_target_per90), 2) : '—'}
                                {' · '}
                                Impatto: {p.impact_score != null ? formatNum(Number(p.impact_score), 2) : '—'}
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
                    <span className="text-slate-500"> (per partite future è di solito no, finché non giocate)</span>
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
                      Campione storico limitato: pochi scontri diretti conclusi disponibili; i conteggi riflettono solo
                      partite giocate e finite.
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
                          {((h2h as Record<string, unknown>).last_5 as Record<string, unknown>[]).map((row, i) => (
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
                          ))}
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

