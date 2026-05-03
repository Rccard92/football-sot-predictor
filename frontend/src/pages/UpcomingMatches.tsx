import { useCallback, useEffect, useState } from 'react'
import {
  DEFAULT_SEASON,
  buildUpcomingSotFeatures,
  evaluateSotLine,
  generateUpcomingSotPredictions,
  getUpcomingPredictions,
  type EvaluateSotLineResponse,
  type UpcomingMatchRow,
  type UpcomingSidePrediction,
} from '../lib/api'

const SEASON = DEFAULT_SEASON

function formatKickoff(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('it-IT', { dateStyle: 'medium', timeStyle: 'short' })
}

const DEBUG_LABELS: Record<string, string> = {
  season_avg_sot_for: 'Media stagionale tiri in porta fatti',
  home_away_avg_sot_for: 'Media casa/fuori tiri in porta fatti',
  last5_avg_sot_for: 'Media ultime 5 partite (tiri in porta fatti)',
  opponent_season_avg_sot_conceded: 'Media stagionale tiri in porta concessi all’avversario',
  opponent_last5_avg_sot_conceded: 'Media ultime 5 tiri in porta concessi all’avversario',
  previous_matches_count: 'Partite storiche considerate',
  fallback_used: 'Dati parziali / fallback usato',
}

function TechnicalAccordion({ debug }: { debug: Record<string, unknown> }) {
  return (
    <details className="mt-3 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-sm">
      <summary className="cursor-pointer font-medium text-slate-700">Mostra dettaglio modello</summary>
      <dl className="mt-3 space-y-2 border-t border-slate-200/80 pt-3">
        {Object.entries(debug).map(([k, v]) => (
          <div key={k} className="flex flex-col gap-0.5 sm:flex-row sm:justify-between">
            <dt className="text-slate-600">{DEBUG_LABELS[k] ?? k}</dt>
            <dd className="font-medium tabular-nums text-slate-900">
              {typeof v === 'boolean' ? (v ? 'Sì' : 'No') : v === null || v === undefined ? '—' : String(v)}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  )
}

function LineEvaluator({
  expectedSot,
  teamLabel,
}: {
  expectedSot: number
  teamLabel: string
}) {
  const [line, setLine] = useState('4.5')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<EvaluateSotLineResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)

  return (
    <div className="mt-4 rounded-xl border border-slate-200 bg-white/80 p-3">
      <p className="text-xs font-medium text-slate-500">Simulazione linea bookmaker ({teamLabel})</p>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end">
        <label className="flex-1 text-xs text-slate-600">
          Linea bookmaker
          <input
            type="number"
            step="0.5"
            min={0}
            max={30}
            value={line}
            onChange={(e) => setLine(e.target.value)}
            placeholder="es. 4.5"
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
        </label>
        <button
          type="button"
          disabled={loading}
          className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-900 disabled:opacity-50"
          onClick={async () => {
            setLoading(true)
            setErr(null)
            setResult(null)
            try {
              const lv = Number(line)
              if (Number.isNaN(lv)) throw new Error('Linea non valida')
              const out = await evaluateSotLine(expectedSot, lv)
              setResult(out)
            } catch (e) {
              setErr(e instanceof Error ? e.message : String(e))
            } finally {
              setLoading(false)
            }
          }}
        >
          {loading ? 'Valutazione…' : 'Valuta linea'}
        </button>
      </div>
      {err ? <p className="mt-2 text-xs text-rose-700">{err}</p> : null}
      {result ? (
        <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-800">
          <p className="font-semibold">{result.label}</p>
          <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">
            {result.suggestion === 'no_bet'
              ? 'No bet'
              : result.suggestion === 'over'
                ? 'Over'
                : 'Under'}{' '}
            · Forza: {result.strength}
          </p>
          <p className="mt-2 text-xs leading-relaxed text-slate-600">{result.explanation}</p>
        </div>
      ) : null}
    </div>
  )
}

function TeamColumn({
  team,
  pred,
  teamLabel,
}: {
  team: UpcomingMatchRow['home_team']
  pred: UpcomingSidePrediction | null
  teamLabel: string
}) {
  return (
    <div className="flex flex-1 flex-col rounded-2xl border border-slate-100 bg-slate-50/50 p-4">
      <div className="flex items-center gap-3">
        {team.logo_url ? (
          <img src={team.logo_url} alt="" className="h-10 w-10 shrink-0 object-contain" />
        ) : (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-200 text-xs font-bold text-slate-600">
            {team.name.slice(0, 2).toUpperCase()}
          </div>
        )}
        <div>
          <p className="font-semibold text-slate-900">{team.name}</p>
        </div>
      </div>
      {pred ? (
        <>
          <p className="mt-4 text-xs text-slate-500">Tiri in porta attesi</p>
          <p className="text-3xl font-bold tabular-nums tracking-tight text-slate-900">
            {pred.expected_sot.toLocaleString('it-IT', { maximumFractionDigits: 2 })}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Livello: <span className="font-medium">{pred.label}</span>
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Fiducia:{' '}
            <span className="font-medium">
              {pred.confidence_label} ({pred.confidence_score})
            </span>
          </p>
          <p className="mt-3 text-sm leading-relaxed text-slate-700">{pred.simple_explanation}</p>
          <LineEvaluator expectedSot={pred.expected_sot} teamLabel={teamLabel} />
          <TechnicalAccordion debug={pred.technical_debug} />
        </>
      ) : (
        <p className="mt-4 text-sm text-slate-500">Nessuna previsione disponibile per questa squadra.</p>
      )}
    </div>
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

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6">
        <header className="pt-4">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Prossima giornata</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Previsioni sui tiri in porta squadra per le prossime partite. Le linee bookmaker sono solo
            simulate, senza quote reali.
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
              Non ci sono ancora previsioni SOT per le partite programmate. Costruisci prima le feature
              sulle partite future, poi genera le prediction.
            </p>
            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                disabled={buildBusy || predBusy}
                className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50 disabled:opacity-50"
                onClick={async () => {
                  setBuildBusy(true)
                  setActionMsg(null)
                  try {
                    await buildUpcomingSotFeatures(SEASON)
                    setActionMsg('Feature future aggiornate.')
                    await load()
                  } catch (e) {
                    setActionMsg(e instanceof Error ? e.message : String(e))
                  } finally {
                    setBuildBusy(false)
                  }
                }}
              >
                {buildBusy ? 'Caricamento…' : 'Costruisci feature future'}
              </button>
              <button
                type="button"
                disabled={buildBusy || predBusy}
                className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-slate-800 disabled:opacity-50"
                onClick={async () => {
                  setPredBusy(true)
                  setActionMsg(null)
                  try {
                    await generateUpcomingSotPredictions(SEASON)
                    setActionMsg('Prediction future generate.')
                    await load()
                  } catch (e) {
                    setActionMsg(e instanceof Error ? e.message : String(e))
                  } finally {
                    setPredBusy(false)
                  }
                }}
              >
                {predBusy ? 'Caricamento…' : 'Genera prediction future'}
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
              <article
                key={m.fixture_id}
                className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm"
              >
                <div className="border-b border-slate-100 bg-slate-50/60 px-5 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                      {m.round ?? 'Giornata'}
                    </p>
                    <span className="rounded-full bg-slate-200/80 px-2.5 py-0.5 text-xs font-medium text-slate-700">
                      Pre-match
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-slate-600">{formatKickoff(m.kickoff_at)}</p>
                  <p className="mt-2 text-lg font-semibold text-slate-900">
                    {m.home_team.name} <span className="font-normal text-slate-400">vs</span> {m.away_team.name}
                  </p>
                </div>
                <div className="grid gap-4 p-5 md:grid-cols-2">
                  <TeamColumn team={m.home_team} pred={m.home_prediction} teamLabel={m.home_team.name} />
                  <TeamColumn team={m.away_team} pred={m.away_prediction} teamLabel={m.away_team.name} />
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
