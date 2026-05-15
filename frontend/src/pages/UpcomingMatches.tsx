import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  DEFAULT_SEASON,
  buildUpcomingSotFeatures,
  generateUpcomingSotPredictions,
  getModelStatus,
  getUpcomingActive,
  type ModelLimitations,
  type ModelStatusResponse,
  type UpcomingActiveResponse,
} from '../lib/api'
import { MatchCard } from '../components/upcoming'
import { V11_MODEL, filterVersionsForUi, labelForModelVersion } from '../lib/modelVersions'

const SEASON = DEFAULT_SEASON

export function UpcomingMatches() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<ModelStatusResponse | null>(null)
  const [data, setData] = useState<UpcomingActiveResponse | null>(null)
  const [buildBusy, setBuildBusy] = useState(false)
  const [predBusy, setPredBusy] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [selectedModel, setSelectedModel] = useState<string | null>(null)
  const didInitModel = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const s = await getModelStatus(SEASON)
      setStatus(s)
      const recommended = s.recommended_model_version || s.active_model_version || null
      if (!didInitModel.current) {
        if (s.recommended_model_version) setSelectedModel(s.recommended_model_version)
        else if (s.active_model_version) setSelectedModel(s.active_model_version)
        didInitModel.current = true
      }
      const mv = selectedModel || recommended
      const res = await getUpcomingActive(SEASON, { limit: 20, onlyNextRound: true, modelVersion: mv })
      setData(res)
    } catch (e) {
      setData(null)
      setStatus(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selectedModel])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('sot_admin_refresh_upcoming')
      if (!raw) return
      const ts = Number(raw)
      if (!Number.isFinite(ts) || Date.now() - ts > 120_000) {
        sessionStorage.removeItem('sot_admin_refresh_upcoming')
        return
      }
      sessionStorage.removeItem('sot_admin_refresh_upcoming')
      void load()
    } catch {
      /* ignore */
    }
  }, [load])

  const hasPredictions = data?.matches?.some((m) => Boolean(m.home_prediction && m.away_prediction)) ?? false

  const limitations: ModelLimitations =
    data?.model_limitations ?? {
      lineups_considered: false,
      injuries_considered: false,
      odds_automatically_imported: false,
      note:
        'Questa versione baseline usa solo statistiche squadra storiche. Formazioni, assenze e quote bookmaker automatiche non sono ancora considerate.',
    }

  const activeModel = status?.active_model_version ?? null
  const recommendedModel = status?.recommended_model_version ?? null
  const modelInView = selectedModel ?? null
  const isDifferentFromActive = Boolean(activeModel && modelInView && activeModel !== modelInView)
  const isRecommendedView =
    Boolean(recommendedModel && modelInView && recommendedModel === modelInView)

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6">
        <header className="pt-4 space-y-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Prossima giornata</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">
              Qual è la previsione del <strong>modello attivo</strong> per le prossime partite (con confronto vs baseline
              v0.1).
            </p>
          </div>

          <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-700 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <p className="font-semibold text-slate-900">
                Modello attivo:{' '}
                <span className="font-normal text-slate-800">
                  {status?.active_model_version ?? '—'}
                </span>
                {isRecommendedView && recommendedModel === activeModel ? (
                  <span className="ml-2 text-[11px] font-medium text-emerald-700">(raccomandato)</span>
                ) : null}
                {modelInView === V11_MODEL ? (
                  <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold text-indigo-800">
                    Stage: Produzione offensiva only
                  </span>
                ) : null}
              </p>
              {recommendedModel && recommendedModel !== activeModel ? (
                <p className="text-xs text-slate-600">
                  Modello raccomandato:{' '}
                  <span className="font-medium text-slate-900">{recommendedModel}</span>
                </p>
              ) : null}
              {isDifferentFromActive ? (
                <p className="text-xs text-slate-600">
                  Modello in vista:{' '}
                  <span className="font-medium text-slate-900">
                    {modelInView}
                  </span>
                </p>
              ) : null}
              <div className="pt-2">
                <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Seleziona modello</label>
                <select
                  value={selectedModel ?? status?.recommended_model_version ?? ''}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900 shadow-sm"
                >
                  {filterVersionsForUi(status?.available_model_versions ?? [])
                    .sort((a, b) => {
                      const rec = status?.recommended_model_version
                      if (a.model_version === rec) return -1
                      if (b.model_version === rec) return 1
                      if (a.model_version === V11_MODEL) return -1
                      if (b.model_version === V11_MODEL) return 1
                      return a.model_version.localeCompare(b.model_version)
                    })
                    .map((v) => (
                    <option key={v.model_version} value={v.model_version}>
                      {labelForModelVersion(v.model_version)}
                      {v.model_version === status?.recommended_model_version ? ' (consigliato)' : ''}
                      {v.is_available_for_upcoming ? '' : ' (no upcoming)'}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="space-y-2 text-xs text-slate-600">
              {data?.round ? (
                <p>
                  Prossimo turno:{' '}
                  <span className="font-medium text-slate-900">{data.round}</span>
                </p>
              ) : null}
              <p className="text-xs text-slate-500">
                Dettagli tecnici in <Link to="/match-variable-audit" className="font-medium text-slate-700 underline">Audit Variabili</Link> e in <Link to="/match-analysis-framework" className="font-medium text-slate-700 underline">Framework Analisi</Link>.
              </p>
            </div>
          </div>
        </header>

        {!loading && !error && data?.warnings?.length ? (
          <details className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-950 shadow-sm">
            <summary className="cursor-pointer select-none font-medium">
              Warning modello (tecnico)
            </summary>
            <ul className="mt-2 list-inside list-disc space-y-1 text-sm">
              {data.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </details>
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
            <details className="mt-4 rounded-2xl border border-amber-200 bg-white/40">
              <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-amber-950 marker:hidden [&::-webkit-details-marker]:hidden">
                Strumenti tecnici (build/generate)
              </summary>
              <div className="border-t border-amber-200 px-4 py-4">
                <div className="flex flex-col gap-3 sm:flex-row">
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
              </div>
            </details>
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
              />
            ))}

            <section className="rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-600 shadow-sm">
              <p className="font-semibold text-slate-900">Nota modello</p>
              <p className="mt-1">{limitations.note}</p>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
