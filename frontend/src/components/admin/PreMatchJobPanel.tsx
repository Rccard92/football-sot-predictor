import { useState } from 'react'
import {
  AdminHttpError,
  DEFAULT_SEASON,
  postPreMatchOfficialLineupRefreshJob,
  type PreMatchJobResultRow,
  type PreMatchJobSummary,
} from '../../lib/api'

function formatPreMatchJobError(e: unknown): string {
  if (e instanceof AdminHttpError) {
    const d = String(e.message)
    if (e.status === 401 && d.includes('Credenziali job')) {
      return 'Errore autenticazione cron: secret non valido (solo per chiamate esterne con X-Admin-Cron-Secret).'
    }
    if (e.status === 503 && d.includes('CRON_SECRET')) {
      return 'CRON_SECRET non configurato sul server. Aggiungilo nelle variabili Railway del backend (solo per il cron).'
    }
    if (e.status === 400 && d.includes('SportAPI')) {
      return `SportAPI non disponibile: ${d}`
    }
    return d || `Errore HTTP ${e.status}`
  }
  return e instanceof Error ? e.message : String(e)
}

export function PreMatchJobPanel() {
  const [busy, setBusy] = useState(false)
  const [last, setLast] = useState<PreMatchJobSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const run = async () => {
    if (
      !window.confirm(
        'Eseguire il job formazioni ufficiali pre-match per le partite in finestra kickoff (~30 min)?',
      )
    ) {
      return
    }
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      const out = await postPreMatchOfficialLineupRefreshJob(
        { season: DEFAULT_SEASON, force: false, minutes_before: 30, window_minutes: 10 },
        { timeoutMs: 600_000 },
      )
      setLast(out)
      const eligible = out.eligible_fixtures ?? 0
      const refreshed = out.refreshed ?? 0
      if (eligible === 0 && refreshed === 0) {
        setInfo(
          'Job completato: nessuna partita eleggibile nella finestra kickoff (~30 min). Riprova più vicino al calcio d’inizio.',
        )
      } else {
        setInfo('Job eseguito correttamente.')
      }
    } catch (e) {
      setError(formatPreMatchJobError(e))
    } finally {
      setBusy(false)
    }
  }

  const results = (last?.results ?? []) as PreMatchJobResultRow[]

  return (
    <section className="rounded-xl border border-violet-200 bg-violet-50/40 p-4">
      <h3 className="text-sm font-semibold text-violet-950">Job formazioni ufficiali pre-match</h3>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
        Aggiorna le formazioni delle partite vicine al kickoff e sincronizza Prossima giornata e Monitoraggio
        Giocate. Il cron Railway lo esegue automaticamente ogni 5 minuti; questo pulsante serve per test o
        forzatura manuale.
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={() => void run()}
        className="mt-3 rounded-md border border-violet-400 bg-white px-3 py-1.5 text-[11px] font-medium text-violet-900 hover:bg-violet-100 disabled:opacity-50"
      >
        {busy ? 'Job in esecuzione…' : 'Esegui job ora'}
      </button>
      {error ? <p className="mt-2 text-[11px] text-rose-700">{error}</p> : null}
      {info && !error ? <p className="mt-2 text-[11px] text-slate-700">{info}</p> : null}
      {last ? (
        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-[11px] text-emerald-950">
          <p className="font-semibold">Ultimo risultato</p>
          <ul className="mt-1 list-inside list-disc">
            <li>
              {last.checked_fixtures ?? last.checked} in finestra · {last.eligible_fixtures ?? '—'} eleggibili
            </li>
            <li>{last.refreshed} formazioni aggiornate</li>
            {last.skipped_recent != null ? <li>{last.skipped_recent} saltate (refresh recente)</li> : null}
            <li>
              {last.created_monitoring_picks ?? last.picks_created} pick create ·{' '}
              {last.updated_monitoring_picks ?? last.picks_updated} aggiornate
            </li>
            {last.lineup_confirmed != null ? <li>{last.lineup_confirmed} con formazione ufficiale</li> : null}
            {last.errors?.length ? <li>{last.errors.length} errori</li> : null}
          </ul>
          {results.length > 0 ? (
            <div className="mt-2 overflow-x-auto">
              <table className="min-w-full text-left text-[10px]">
                <thead>
                  <tr className="text-slate-600">
                    <th className="pr-2 py-1">Match</th>
                    <th className="pr-2 py-1">Kickoff</th>
                    <th className="pr-2 py-1">Δ SOT</th>
                    <th className="py-1">Monitoraggio</th>
                  </tr>
                </thead>
                <tbody>
                  {results.slice(0, 8).map((r) => (
                    <tr key={r.fixture_id} className="border-t border-emerald-100/80">
                      <td className="py-1 pr-2">{r.match ?? r.match_name ?? r.fixture_id}</td>
                      <td className="py-1 pr-2 tabular-nums">{r.kickoff ? r.kickoff.slice(0, 16) : '—'}</td>
                      <td className="py-1 pr-2 tabular-nums">
                        {r.delta_total_sot != null
                          ? `${r.before_total_sot ?? '?'} → ${r.after_total_sot ?? '?'} (${r.delta_total_sot >= 0 ? '+' : ''}${r.delta_total_sot})`
                          : '—'}
                      </td>
                      <td className="py-1">{r.monitoring_pick_status ?? r.status ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
