import { useState } from 'react'
import { DEFAULT_SEASON, postPreMatchLineupRefreshJob, type PreMatchJobSummary } from '../../lib/api'

export function PreMatchJobPanel() {
  const [busy, setBusy] = useState(false)
  const [last, setLast] = useState<PreMatchJobSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    if (!window.confirm('Eseguire il job pre-match per le partite in finestra kickoff (~30 min)?')) return
    setBusy(true)
    setError(null)
    try {
      const out = await postPreMatchLineupRefreshJob(
        { season: DEFAULT_SEASON, force: false },
        { timeoutMs: 600_000 },
      )
      setLast(out)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-violet-200 bg-violet-50/40 p-4">
      <h3 className="text-sm font-semibold text-violet-950">Job pre-match formazioni</h3>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
        Aggiorna SportAPI e salva il pronostico definitivo per le partite che iniziano tra circa 30 minuti. Su
        Railway configura un cron ogni 5 minuti su{' '}
        <code className="rounded bg-white/80 px-1 text-[10px]">POST /api/admin/jobs/pre-match-lineup-refresh/run</code>{' '}
        con header <code className="rounded bg-white/80 px-1 text-[10px]">X-Admin-Cron-Secret</code>.
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={() => void run()}
        className="mt-3 rounded-md border border-violet-400 bg-white px-3 py-1.5 text-[11px] font-medium text-violet-900 hover:bg-violet-100 disabled:opacity-50"
      >
        {busy ? 'Job in esecuzione…' : 'Esegui ora job pre-match'}
      </button>
      {error ? <p className="mt-2 text-[11px] text-rose-700">{error}</p> : null}
      {last ? (
        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-[11px] text-emerald-950">
          <p className="font-semibold">Ultimo risultato</p>
          <ul className="mt-1 list-inside list-disc">
            <li>{last.checked} partite controllate</li>
            <li>{last.refreshed} formazioni aggiornate</li>
            <li>
              {last.picks_created} pick creati · {last.picks_updated} aggiornati · {last.skipped} saltati
            </li>
            {last.lineup_confirmed != null ? <li>{last.lineup_confirmed} con formazione ufficiale</li> : null}
            {last.errors?.length ? <li>{last.errors.length} errori</li> : null}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
