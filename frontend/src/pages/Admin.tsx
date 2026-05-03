import { useState } from 'react'
import {
  DEFAULT_SEASON,
  adminBootstrapSerieA,
  adminIngestTeamStats,
  buildUpcomingSotFeatures,
  generateUpcomingSotPredictions,
  runBuildSotFeatures,
  runGenerateSotPredictions,
  runSotBacktest,
} from '../lib/api'

const SEASON = DEFAULT_SEASON

type Btn = { id: string; label: string; run: () => Promise<unknown> }

function adminPickMessage(payload: unknown, ok: string): string {
  if (payload && typeof payload === 'object') {
    const o = payload as Record<string, unknown>
    if (typeof o.message === 'string' && o.message.trim()) return o.message
  }
  return ok
}

export function Admin() {
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const actions: Btn[] = [
    {
      id: 'bootstrap',
      label: 'Importa calendario / squadre',
      run: () => adminBootstrapSerieA(SEASON),
    },
    {
      id: 'team-stats',
      label: 'Importa statistiche squadra',
      run: () => adminIngestTeamStats(SEASON),
    },
    {
      id: 'feat',
      label: 'Costruisci feature completate',
      run: () => runBuildSotFeatures(SEASON),
    },
    {
      id: 'pred',
      label: 'Genera prediction completate',
      run: () => runGenerateSotPredictions(SEASON),
    },
    {
      id: 'bt',
      label: 'Esegui backtest',
      run: () => runSotBacktest(SEASON),
    },
    {
      id: 'feat-up',
      label: 'Costruisci feature future',
      run: () => buildUpcomingSotFeatures(SEASON),
    },
    {
      id: 'pred-up',
      label: 'Genera prediction future',
      run: () => generateUpcomingSotPredictions(SEASON),
    },
  ]

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-3xl space-y-6 px-4 sm:px-6">
        <header className="pt-4">
          <h1 className="text-2xl font-semibold text-slate-900">Admin</h1>
          <p className="mt-2 text-sm text-slate-600">
            Operazioni di ingestion e rigenerazione dati. Richiedono chiavi API sul server dove necessario.
          </p>
          <p className="mt-1 text-xs text-slate-500">Stagione {SEASON}</p>
        </header>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-3">
            {actions.map((a) => (
              <button
                key={a.id}
                type="button"
                disabled={loadingId !== null}
                className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-medium text-slate-800 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                onClick={async () => {
                  setLoadingId(a.id)
                  setMsg(null)
                  try {
                    const out = await a.run()
                    setMsg({
                      ok: true,
                      text: adminPickMessage(
                        out,
                        a.id === 'bootstrap' ? 'Bootstrap avviato.' : 'Operazione completata.',
                      ),
                    })
                  } catch (e) {
                    setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
                  } finally {
                    setLoadingId(null)
                  }
                }}
              >
                {loadingId === a.id ? 'In corso…' : a.label}
              </button>
            ))}
          </div>
          {msg ? (
            <p
              className={`mt-4 rounded-lg px-3 py-2 text-sm ${
                msg.ok ? 'bg-emerald-50 text-emerald-900' : 'bg-rose-50 text-rose-900'
              }`}
            >
              {msg.text}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
