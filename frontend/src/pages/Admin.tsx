import { useState } from 'react'
import {
  DEFAULT_SEASON,
  adminBootstrapSerieA,
  adminIngestAvailability,
  adminIngestLineups,
  adminIngestPlayerStats,
  adminIngestTeamStats,
  adminTestInjuriesApi,
  buildPlayerSotProfiles,
  buildUpcomingSotFeatures,
  generateUpcomingSotPredictions,
  getPlayerSotProfilesSummary,
  runBuildSotFeatures,
  runGenerateSotPredictions,
  runSotBacktest,
} from '../lib/api'

const SEASON = DEFAULT_SEASON

type Btn = { id: string; label: string; description?: string; run: () => Promise<unknown> }

function adminPickMessage(payload: unknown, ok: string): string {
  if (payload && typeof payload === 'object') {
    const o = payload as Record<string, unknown>
    if (typeof o.message === 'string' && o.message.trim()) return o.message
    if (typeof o.status === 'string' && o.status === 'skipped' && typeof o.reason === 'string') {
      return `Operazione saltata: ${o.reason}`
    }
  }
  return ok
}

type AdminMsg = { ok: boolean; text: string; json?: unknown }

export function Admin() {
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [msg, setMsg] = useState<AdminMsg | null>(null)

  const baseActions: Btn[] = [
    {
      id: 'bootstrap',
      label: 'Importa calendario e squadre',
      description: 'Bootstrap Serie A dalla API Football.',
      run: () => adminBootstrapSerieA(SEASON),
    },
    {
      id: 'team-stats',
      label: 'Importa statistiche di squadra (partite finite)',
      run: () => adminIngestTeamStats(SEASON),
    },
  ]

  const layerActions: Btn[] = [
    {
      id: 'player-stats',
      label: 'Importa statistiche giocatori (partite finite)',
      run: () => adminIngestPlayerStats(SEASON),
    },
    {
      id: 'lineups',
      label: 'Importa formazioni (partite finite)',
      run: () => adminIngestLineups(SEASON),
    },
    {
      id: 'injuries-test',
      label: 'Prova endpoint infortuni API (lettura)',
      run: () => adminTestInjuriesApi(SEASON),
    },
    {
      id: 'availability',
      label: 'Importa disponibilità / infortuni (prudente)',
      run: () => adminIngestAvailability(SEASON),
    },
    {
      id: 'profiles-build',
      label: 'Calcola profili impatto giocatori (stagione)',
      run: () => buildPlayerSotProfiles(SEASON),
    },
    {
      id: 'profiles-summary',
      label: 'Mostra riepilogo profili (GET)',
      run: () => getPlayerSotProfilesSummary(SEASON),
    },
  ]

  const modelActions: Btn[] = [
    {
      id: 'feat',
      label: 'Costruisci feature completate',
      run: () => runBuildSotFeatures(SEASON),
    },
    {
      id: 'pred',
      label: 'Genera previsioni completate',
      run: () => runGenerateSotPredictions(SEASON),
    },
    {
      id: 'bt',
      label: 'Esegui backtest',
      run: () => runSotBacktest(SEASON),
    },
    {
      id: 'feat-up',
      label: 'Costruisci feature partite future',
      run: () => buildUpcomingSotFeatures(SEASON),
    },
    {
      id: 'pred-up',
      label: 'Genera previsioni partite future',
      run: () => generateUpcomingSotPredictions(SEASON),
    },
  ]

  const runBtn = async (a: Btn) => {
    setLoadingId(a.id)
    setMsg(null)
    try {
      const out = await a.run()
      const text =
        a.id === 'bootstrap'
          ? adminPickMessage(out, 'Bootstrap avviato.')
          : a.id === 'injuries-test' || a.id === 'profiles-summary'
            ? adminPickMessage(out, 'Risposta ricevuta.')
            : adminPickMessage(out, 'Operazione completata.')
      const showJson = a.id === 'injuries-test' || a.id === 'profiles-summary'
      setMsg({ ok: true, text, json: showJson ? out : undefined })
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoadingId(null)
    }
  }

  const loadDataLayers = async () => {
    setLoadingId('load-layers')
    setMsg(null)
    try {
      await adminIngestTeamStats(SEASON)
      await adminIngestPlayerStats(SEASON)
      await adminIngestLineups(SEASON)
      setMsg({
        ok: true,
        text:
          'Importazione completata: statistiche squadra, statistiche giocatori e formazioni storiche. Aggiorna la dashboard per vedere le percentuali di copertura.',
      })
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoadingId(null)
    }
  }

  const renderButtons = (actions: Btn[]) => (
    <div className="flex flex-col gap-3">
      {actions.map((a) => (
        <button
          key={a.id}
          type="button"
          disabled={loadingId !== null}
          className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-medium text-slate-800 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          onClick={() => void runBtn(a)}
        >
          <span className="block">{loadingId === a.id ? 'In corso…' : a.label}</span>
          {a.description ? (
            <span className="mt-1 block text-xs font-normal text-slate-500">{a.description}</span>
          ) : null}
        </button>
      ))}
    </div>
  )

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
          <h2 className="text-sm font-semibold text-slate-900">Calendario e dati squadra</h2>
          <p className="mt-1 text-xs text-slate-600">Primi passi per popolare il campionato.</p>
          <div className="mt-4">{renderButtons(baseActions)}</div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Layer giocatori, formazioni, disponibilità</h2>
          <p className="mt-1 text-xs text-slate-600">
            Dati aggiuntivi per analisi e dashboard: non modificano da soli la formula baseline dei tiri in porta.
          </p>
          <div className="mt-4">{renderButtons(layerActions)}</div>
          <button
            type="button"
            disabled={loadingId !== null}
            className="mt-4 w-full rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-left text-sm font-semibold text-indigo-950 transition hover:bg-indigo-100/80 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => void loadDataLayers()}
          >
            {loadingId === 'load-layers' ? 'In corso…' : 'Importa in sequenza: squadra + giocatori + formazioni'}
          </button>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Feature, previsioni e backtest</h2>
          <p className="mt-1 text-xs text-slate-600">Pipeline del modello baseline v0.1.</p>
          <div className="mt-4">{renderButtons(modelActions)}</div>
        </div>

        {msg ? (
          <div
            className={`rounded-2xl border px-4 py-3 text-sm shadow-sm ${
              msg.ok
                ? 'border-emerald-200 bg-emerald-50/90 text-emerald-950'
                : 'border-rose-200 bg-rose-50/90 text-rose-950'
            }`}
          >
            <p>{msg.text}</p>
            {msg.json !== undefined ? (
              <pre className="mt-3 max-h-80 overflow-auto rounded-lg bg-white/80 p-3 text-xs text-slate-800 ring-1 ring-slate-200/80">
                {JSON.stringify(msg.json, null, 2)}
              </pre>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
