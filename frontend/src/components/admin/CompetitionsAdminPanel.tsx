import { useMemo, useState } from 'react'
import {
  backfillSerieACompetition,
  bootstrapCompetition,
  buildCompetitionPlayerProfiles,
  createCompetition,
  discoverCompetitions,
  ingestCompetitionPlayerStats,
  ingestCompetitionTeamStats,
  refreshCompetitionNextRound,
  DEFAULT_SEASON,
  type CompetitionDiscoverCandidate,
} from '../../lib/api'
import { useCompetition } from '../../contexts/CompetitionContext'

type IngestionAction = {
  label: string
  fn: () => Promise<Record<string, unknown>>
}

function DiscoverCandidateCard({
  candidate,
  selected,
  onSelect,
}: {
  candidate: CompetitionDiscoverCandidate
  selected: boolean
  onSelect: () => void
}) {
  return (
    <div
      className={`rounded-lg border px-3 py-2 text-sm ${
        selected ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 bg-white'
      }`}
    >
      <div className="flex flex-wrap items-start gap-3">
        {candidate.logo ? (
          <img
            src={candidate.logo}
            alt=""
            className="h-8 w-8 rounded object-contain"
          />
        ) : null}
        <div className="min-w-0 flex-1">
          <p className="font-medium text-slate-900">{candidate.name}</p>
          <p className="text-xs text-slate-600">
            id {candidate.provider_league_id} · {candidate.country ?? '?'} · {candidate.season}
            {candidate.season_current ? ' · current' : ''}
          </p>
        </div>
        <button
          type="button"
          className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-800 hover:bg-slate-50"
          onClick={onSelect}
        >
          Seleziona candidato
        </button>
      </div>
      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-slate-500">Raw payload</summary>
        <pre className="mt-1 max-h-40 overflow-auto rounded bg-slate-50 p-2 text-[10px]">
          {JSON.stringify(candidate.raw_payload ?? candidate, null, 2)}
        </pre>
      </details>
    </div>
  )
}

function DiscoverCandidateList({
  title,
  candidates,
  selectedCandidateId,
  onSelect,
}: {
  title: string
  candidates: CompetitionDiscoverCandidate[]
  selectedCandidateId: number | null
  onSelect: (id: number) => void
}) {
  if (candidates.length === 0) return null

  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      {candidates.map((candidate) => (
        <DiscoverCandidateCard
          key={candidate.provider_league_id}
          candidate={candidate}
          selected={selectedCandidateId === candidate.provider_league_id}
          onSelect={() => onSelect(candidate.provider_league_id)}
        />
      ))}
    </div>
  )
}

export function CompetitionsAdminPanel() {
  const {
    selectedCompetition,
    selectedCompetitionId,
    refreshCompetitions,
    setSelectedCompetitionId,
  } = useCompetition()
  const [country, setCountry] = useState('Brazil')
  const [nameQuery, setNameQuery] = useState('Serie A')
  const [season, setSeason] = useState(2026)
  const [candidates, setCandidates] = useState<CompetitionDiscoverCandidate[]>([])
  const [otherCandidates, setOtherCandidates] = useState<CompetitionDiscoverCandidate[]>([])
  const [selectedCandidateId, setSelectedCandidateId] = useState<number | null>(null)
  const [discoverMessage, setDiscoverMessage] = useState<string | null>(null)
  const [apiQuery, setApiQuery] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [log, setLog] = useState<string | null>(null)
  const [dryRun, setDryRun] = useState(true)

  const selectedCandidate = useMemo(
    () =>
      [...candidates, ...otherCandidates].find(
        (c) => c.provider_league_id === selectedCandidateId,
      ) ?? null,
    [candidates, otherCandidates, selectedCandidateId],
  )

  const run = async (label: string, fn: () => Promise<Record<string, unknown>>) => {
    setBusy(label)
    setLog(null)
    try {
      const res = await fn()
      setLog(JSON.stringify(res, null, 2))
      return res
    } catch (e) {
      setLog(e instanceof Error ? e.message : String(e))
      return null
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

      <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
        <h3 className="text-sm font-semibold text-emerald-900">Serie A esistente</h3>
        <p className="mt-1 text-sm text-emerald-800">
          Crea la competition Serie A Italia 2025 e collega i dati già presenti.
        </p>
        <button
          type="button"
          className="mt-3 rounded-lg bg-emerald-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          disabled={!!busy}
          onClick={() =>
            void (async () => {
              const res = await run('backfill-serie-a', async () => {
                const summary = await backfillSerieACompetition(DEFAULT_SEASON)
                return summary as unknown as Record<string, unknown>
              })
              if (res && typeof res.competition_id === 'number') {
                await refreshCompetitions()
                if (selectedCompetitionId == null) {
                  setSelectedCompetitionId(Number(res.competition_id))
                }
              }
            })()
          }
        >
          Backfill Serie A esistente
        </button>
      </div>

      <div className="mt-6 border-t border-slate-200 pt-4">
        <h3 className="text-sm font-semibold text-slate-900">Discovery Brasileirão</h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
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
              placeholder="Serie A, Brasileirão…"
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
                setCandidates(res.candidates ?? [])
                setOtherCandidates(res.other_candidates ?? [])
                setSelectedCandidateId(null)
                setDiscoverMessage(res.message ?? null)
                setApiQuery(res.api_query ?? null)
                return res as unknown as Record<string, unknown>
              })
            }
          >
            Discovery API-Sports
          </button>
          <button
            type="button"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
            disabled={!!busy || selectedCandidate == null}
            onClick={() =>
              void run('create', async () => {
                if (selectedCandidate == null) {
                  throw new Error('Prima esegui Discovery API-Sports e seleziona una lega candidata.')
                }
                const c = await createCompetition({
                  key: `brasileirao_serie_a_${season}`,
                  name: 'Brasileirão Série A',
                  country: 'Brazil',
                  provider_league_id: selectedCandidate.provider_league_id,
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

        {selectedCandidate == null ? (
          <p className="mt-2 text-xs text-amber-700">
            Prima esegui Discovery API-Sports e seleziona una lega candidata.
          </p>
        ) : (
          <p className="mt-2 text-xs text-indigo-700">
            Candidato selezionato: {selectedCandidate.name} (id {selectedCandidate.provider_league_id})
          </p>
        )}

        {apiQuery ? (
          <p className="mt-2 text-xs text-slate-500">Query API: GET /leagues?{apiQuery}</p>
        ) : null}

        {discoverMessage ? <p className="mt-2 text-xs text-slate-600">{discoverMessage}</p> : null}

        <DiscoverCandidateList
          title="Candidati principali"
          candidates={candidates}
          selectedCandidateId={selectedCandidateId}
          onSelect={setSelectedCandidateId}
        />

        <DiscoverCandidateList
          title="Altri risultati del paese"
          candidates={otherCandidates}
          selectedCandidateId={selectedCandidateId}
          onSelect={setSelectedCandidateId}
        />
      </div>

      {selectedCompetitionId != null ? (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-200 pt-4">
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
