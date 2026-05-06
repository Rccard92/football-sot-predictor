import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  DEFAULT_SEASON,
  buildUpcomingSotFeatures,
  generateUpcomingSotPredictions,
  getUpcomingPredictions,
  getUpcomingV02PlayerAdjusted,
  type ModelLimitations,
  type UpcomingPlayerAdjustedResponse,
} from '../lib/api'
import { MatchCard } from '../components/upcoming'

const SEASON = DEFAULT_SEASON

export function UpcomingMatches() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<Awaited<ReturnType<typeof getUpcomingPredictions>> | null>(null)
  const [buildBusy, setBuildBusy] = useState(false)
  const [predBusy, setPredBusy] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [dataPlayerAdjusted, setDataPlayerAdjusted] = useState<UpcomingPlayerAdjustedResponse | null>(null)
  const [viewMode, setViewMode] = useState<'player_adjusted' | 'v01'>('player_adjusted')
  const [paAvailable, setPaAvailable] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getUpcomingPredictions(SEASON, { limit: 20, onlyNextRound: true })
      const resPA = await getUpcomingV02PlayerAdjusted(SEASON, { limit: 20, onlyNextRound: true })
      setData(res)
      setDataPlayerAdjusted(resPA)
      setPaAvailable(resPA?.status === 'success' && (resPA.matches?.some((m) => Boolean(m.home && m.away)) ?? false))
    } catch (e) {
      setData(null)
      setDataPlayerAdjusted(null)
      setPaAvailable(false)
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
  const usePlayerAdjustedView = viewMode === 'player_adjusted' && Boolean(paAvailable)

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6">
        <header className="pt-4 space-y-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Prossima giornata</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">
              Stime sui <strong>tiri in porta</strong> per le prossime partite. I numeri mostrati sono quelli della
              versione <strong>live v0.2 Player Adjusted</strong>, con baseline v0.1 disponibile come confronto/debug.
            </p>
          </div>

          <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-700 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <p className="font-semibold text-slate-900">
                Modello attivo:{' '}
                <span className="font-normal text-slate-800">
                  baseline_v0_2_player_adjusted
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
              Vista baseline v0.1 (confronto/debug)
            </button>
            <button
              type="button"
              className={`rounded-lg px-2 py-1 ${viewMode === 'player_adjusted' ? 'bg-slate-900 text-white' : 'text-slate-700'}`}
              onClick={() => setViewMode('player_adjusted')}
            >
              Vista v0.2 Player Adjusted
            </button>
          </div>
        </header>

        {!loading && !error && viewMode === 'player_adjusted' && !paAvailable ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-950 shadow-sm">
            La vista v0.2 Player Adjusted non è disponibile per questa giornata: sto mostrando la baseline v0.1 come fallback.
          </div>
        ) : null}

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
              <MatchCard
                key={m.fixture_id}
                match={m}
                limitations={limitations}
                playerAdjustedMatch={dataPlayerAdjusted?.matches.find((x) => x.fixture_id === m.fixture_id) ?? null}
                usePlayerAdjustedView={usePlayerAdjustedView}
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
