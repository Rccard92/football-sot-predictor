import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { MatchExplanationView } from '../components/match-explanation/MatchExplanationView'
import { CompetitionBadge } from '../components/CompetitionSelector'
import { useCompetition } from '../contexts/CompetitionContext'
import {
  getCompetitionAuditFixtures,
  getCompetitionFixtureExplanation,
  type CompetitionAuditFixtureRow,
} from '../lib/api'
import type { SotFixtureExplanationResponse } from '../types/sotExplanation'
import { MODEL_OPTIONS_AUDIT } from '../lib/modelVersions'
import { formatExplanationApiError, formatFetchError } from '../utils/formatFetchError'

const MODEL_OPTIONS = MODEL_OPTIONS_AUDIT

function useQuery(): URLSearchParams {
  const { search } = useLocation()
  return useMemo(() => new URLSearchParams(search), [search])
}

function toFixturesListItem(row: CompetitionAuditFixtureRow) {
  return {
    fixture_id: row.fixture_id,
    api_fixture_id: row.api_fixture_id ?? row.fixture_id,
    round: row.round ?? null,
    kickoff_at: row.kickoff_at ?? row.kickoff ?? '',
    status_short: row.status_short ?? row.status ?? '',
    home_team: row.home_team,
    away_team: row.away_team,
  }
}

export function MatchVariableAudit() {
  const qs = useQuery()
  const navigate = useNavigate()
  const { selectedCompetition, selectedCompetitionId } = useCompetition()

  const competitionIdFromQS = Number(qs.get('competition_id') || '')
  const fixtureIdFromQS = Number(qs.get('fixture_id') || '')
  const modelFromQS = (qs.get('model_version') || '').trim()

  const competitionId =
    Number.isFinite(competitionIdFromQS) && competitionIdFromQS > 0
      ? competitionIdFromQS
      : selectedCompetitionId

  const [fixtures, setFixtures] = useState<CompetitionAuditFixtureRow[]>([])
  const [fixtureId, setFixtureId] = useState<number | null>(
    Number.isFinite(fixtureIdFromQS) && fixtureIdFromQS > 0 ? fixtureIdFromQS : null,
  )
  const [modelVersion, setModelVersion] = useState<string>(
    MODEL_OPTIONS.some((o) => o.value === modelFromQS) ? modelFromQS : '',
  )
  const [fixtureQsMismatch, setFixtureQsMismatch] = useState(false)

  const [loading, setLoading] = useState(false)
  const [fixturesError, setFixturesError] = useState<string | null>(null)
  const [explanationError, setExplanationError] = useState<string | null>(null)
  const [data, setData] = useState<SotFixtureExplanationResponse | null>(null)

  const syncUrl = useCallback(
    (nextFixtureId: number | null, nextModelVersion: string) => {
      if (competitionId == null) return
      const p = new URLSearchParams()
      p.set('competition_id', String(competitionId))
      if (nextFixtureId != null) p.set('fixture_id', String(nextFixtureId))
      if (nextModelVersion) p.set('model_version', nextModelVersion)
      navigate(`/match-variable-audit?${p.toString()}`, { replace: true })
    },
    [competitionId, navigate],
  )

  useEffect(() => {
    const loadFixtures = async () => {
      setFixturesError(null)
      setFixtureQsMismatch(false)
      setFixtures([])
      setData(null)

      if (competitionId == null) {
        setFixturesError('Seleziona un campionato per visualizzare l\'audit.')
        setFixtureId(null)
        return
      }

      try {
        const body = await getCompetitionAuditFixtures(competitionId, {
          scope: 'next_round',
          limit: 40,
        })
        const list = body.fixtures ?? []
        setFixtures(list)

        if (list.length === 0) {
          setFixtureId(null)
          setFixturesError('Nessuna fixture disponibile per il campionato selezionato.')
          return
        }

        const ids = new Set(list.map((f) => f.fixture_id))
        const qsFixtureValid =
          Number.isFinite(fixtureIdFromQS) && fixtureIdFromQS > 0 && ids.has(fixtureIdFromQS)

        if (qsFixtureValid) {
          setFixtureId(fixtureIdFromQS)
        } else if (Number.isFinite(fixtureIdFromQS) && fixtureIdFromQS > 0) {
          setFixtureId(null)
          setFixtureQsMismatch(true)
          setFixturesError('Fixture non disponibile per il campionato selezionato.')
        } else if (fixtureId == null || !ids.has(fixtureId)) {
          setFixtureId(list[0].fixture_id)
        }
      } catch (e) {
        setFixtures([])
        setFixtureId(null)
        setFixturesError(formatFetchError(e, `GET /api/competitions/${competitionId}/predictions/sot/fixtures`))
      }
    }
    void loadFixtures()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [competitionId, fixtureIdFromQS])

  const reloadExplanation = useCallback(async () => {
    if (!fixtureId || competitionId == null || fixtureQsMismatch) return
    setLoading(true)
    setExplanationError(null)
    try {
      const parsed = await getCompetitionFixtureExplanation(competitionId, fixtureId, {
        modelVersion: modelVersion || null,
      })
      if (parsed.status === 'error') {
        setData(null)
        setExplanationError(formatExplanationApiError(parsed))
        return
      }
      setData(parsed)
    } catch (e) {
      setData(null)
      setExplanationError(
        formatFetchError(
          e,
          `GET /api/competitions/${competitionId}/predictions/sot/fixture/${fixtureId}/explanation`,
        ),
      )
    } finally {
      setLoading(false)
    }
  }, [competitionId, fixtureId, fixtureQsMismatch, modelVersion])

  useEffect(() => {
    void reloadExplanation()
  }, [reloadExplanation])

  const handleFixtureChange = (nextId: number | null) => {
    setFixtureId(nextId)
    setFixtureQsMismatch(false)
    syncUrl(nextId, modelVersion)
  }

  const handleModelChange = (nextModel: string) => {
    setModelVersion(nextModel)
    syncUrl(fixtureId, nextModel)
  }

  const fixturesForSelect = fixtures.map(toFixturesListItem)

  return (
    <div className="space-y-6 pb-8">
      <header className="rounded-2xl border border-slate-200/80 bg-white px-4 py-4 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">Spiegazione previsione partita</h1>
        <div className="mt-2">
          <CompetitionBadge />
        </div>
        {competitionId != null ? (
          <p className="mt-1 text-xs text-slate-500">
            competition_id={competitionId}
            {selectedCompetition?.name ? ` · ${selectedCompetition.name}` : ''}
          </p>
        ) : null}
        <p className="mt-1 text-sm text-slate-600">
          Audit read-only: come il modello attivo ha costruito i tiri in porta attesi, usando solo dati già salvati.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <label className="text-xs font-medium text-slate-600" htmlFor="fixture-select">
            Partita
          </label>
          <select
            id="fixture-select"
            className="max-w-xl rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
            value={fixtureId ?? ''}
            onChange={(e) => handleFixtureChange(Number(e.target.value) || null)}
            disabled={fixtures.length === 0 || competitionId == null}
          >
            {fixtures.length === 0 ? (
              <option value="">Nessuna partita futura disponibile</option>
            ) : null}
            {fixturesForSelect.map((f) => (
              <option key={f.fixture_id} value={f.fixture_id}>
                {f.kickoff_at?.slice(0, 10)} — {f.home_team.name} vs {f.away_team.name} ({f.status_short})
              </option>
            ))}
          </select>
          <label className="text-xs font-medium text-slate-600" htmlFor="model-version-select">
            Modello
          </label>
          <select
            id="model-version-select"
            className="max-w-md rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm"
            value={modelVersion}
            onChange={(e) => handleModelChange(e.target.value)}
          >
            {MODEL_OPTIONS.map((o) => (
              <option key={o.value || 'auto'} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      {fixtures.length === 0 && !fixturesError && competitionId != null ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-950">
          Nessuna fixture disponibile per il campionato selezionato.
        </div>
      ) : null}

      {fixturesError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
          {fixturesError}
        </div>
      ) : null}

      {explanationError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
          {explanationError}
        </div>
      ) : null}

      {loading ? (
        <div className="space-y-3">
          <div className="h-24 animate-pulse rounded-2xl bg-slate-200/80" />
          <div className="h-48 animate-pulse rounded-2xl bg-slate-200/80" />
        </div>
      ) : null}

      {!loading && data?.status === 'ok' && data.fixture && data.prediction_summary ? (
        <MatchExplanationView data={data} onDataRefresh={reloadExplanation} />
      ) : null}

      {!loading && data?.status === 'missing' ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-950">
          {data.message ?? 'Dati insufficienti per questa fixture.'}
        </div>
      ) : null}

      {!loading && data?.status === 'experimental_not_ready' ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-950">
          <p className="font-semibold text-amber-950">Modello v2.1 — engine in preparazione</p>
          <p className="mt-1">
            {data.message ??
              'Modello v2.1 registrato, engine di calcolo in preparazione. Nessun fallback su v2.0.'}
          </p>
        </div>
      ) : null}
    </div>
  )
}
