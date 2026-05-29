import { useState } from 'react'
import {
  bootstrapCompetition,
  buildCompetitionPlayerProfiles,
  createCompetition,
  discoverCompetitions,
  ingestCompetitionPlayerStats,
  ingestCompetitionTeamStats,
  refreshCompetitionNextRound,
} from '../../lib/api'
import { useCompetition } from '../../contexts/CompetitionContext'

type IngestionAction = {
  label: string
  fn: () => Promise<Record<string, unknown>>
}

export function CompetitionsAdminPanel() {
  const { selectedCompetition, selectedCompetitionId, refreshCompetitions } = useCompetition()
  const [country, setCountry] = useState('Brazil')
  const [nameQuery, setNameQuery] = useState('Serie A')
  const [season, setSeason] = useState(2026)
  const [discoverResult, setDiscoverResult] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [log, setLog] = useState<string | null>(null)
  const [dryRun, setDryRun] = useState(true)

  const run = async (label: string, fn: () => Promise<Record<string, unknown>>) => {
    setBusy(label)
    setLog(null)
    try {
      const res = await fn()
      setLog(JSON.stringify(res, null, 2))
    } catch (e) {
      setLog(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Campionati</h2>
      <p className="mt-1 text-sm text-slate-600">
        Gestione multi-campionato. Campionato selezionato:{' '}
        <strong>{selectedCompetition?.name ?? '—'}</strong>
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <label className="text-sm">
          Paese
          <input
            className="mt-1 w-full rounded border border-slate-200 px-2 py-1"
            value={country}
            onChange={(e) => setCountry(e.target.value)}
          />
        </label>
        <label className="text-sm">
          Nome lega
          <input
            className="mt-1 w-full rounded border border-slate-200 px-2 py-1"
            value={nameQuery}
            onChange={(e) => setNameQuery(e.target.value)}
          />
        </label>
        <label className="text-sm">
          Stagione
          <input
            type="number"
            className="mt-1 w-full rounded border border-slate-200 px-2 py-1"
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-lg bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          disabled={!!busy}
          onClick={() =>
            void run('discover', async () => {
              const res = await discoverCompetitions({ country, name_query: nameQuery, season })
              setDiscoverResult(JSON.stringify(res, null, 2))
              return res as Record<string, unknown>
            })
          }
        >
          Discovery API-Sports
        </button>
        <button
          type="button"
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={!!busy}
          onClick={() =>
            void run('create', async () => {
              let providerLeagueId: number | null = null
              if (discoverResult) {
                try {
                  const parsed = JSON.parse(discoverResult) as {
                    candidates?: Array<{ provider_league_id?: number }>
                  }
                  providerLeagueId = parsed.candidates?.[0]?.provider_league_id ?? null
                } catch {
                  providerLeagueId = null
                }
              }
              if (providerLeagueId == null) {
                throw new Error('Eseguire prima Discovery e selezionare una lega candidata')
              }
              const c = await createCompetition({
                key: `brasileirao_serie_a_${season}`,
                name: 'Brasileirão Série A',
                country: 'Brazil',
                provider_league_id: providerLeagueId,
                season,
                timezone: 'America/Sao_Paulo',
              })
              await refreshCompetitions()
              return c as unknown as Record<string, unknown>
            })
          }
        >
          Crea Brasileirão (da discovery)
        </button>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          Dry-run import
        </label>
      </div>

      {discoverResult ? (
        <pre className="mt-3 max-h-40 overflow-auto rounded bg-slate-50 p-2 text-xs">{discoverResult}</pre>
      ) : null}

      {selectedCompetitionId != null ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {(
            [
              { label: 'Bootstrap', fn: () => bootstrapCompetition(selectedCompetitionId, dryRun) },
              { label: 'Team stats', fn: () => ingestCompetitionTeamStats(selectedCompetitionId, dryRun) },
              { label: 'Player stats', fn: () => ingestCompetitionPlayerStats(selectedCompetitionId, dryRun) },
              {
                label: 'Profili giocatori',
                fn: () => buildCompetitionPlayerProfiles(selectedCompetitionId, dryRun),
              },
              {
                label: 'Prossima giornata',
                fn: () => refreshCompetitionNextRound(selectedCompetitionId, dryRun),
              },
            ] satisfies IngestionAction[]
          ).map(({ label, fn }) => (
            <button
              key={label}
              type="button"
              className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm text-indigo-900 disabled:opacity-50"
              disabled={!!busy}
              onClick={() => void run(label, fn)}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}

      {log ? <pre className="mt-3 max-h-60 overflow-auto rounded bg-slate-50 p-2 text-xs">{log}</pre> : null}
    </section>
  )
}
