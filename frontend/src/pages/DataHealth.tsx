import { useCallback, useEffect, useState } from 'react'
import { Card } from '../components/ui/Card'
import { ContextBanner } from '../components/ContextBanner'
import { useCompetition } from '../contexts/CompetitionContext'
import { useModelSelection } from '../contexts/ModelSelectionContext'
import { getCompetitionDataHealth } from '../lib/api'
import { labelForModelVersion } from '../lib/modelVersions'

type HealthRow = { label: string; value: string | number | null | undefined }

type ModelHealthDetail = {
  model_version: string
  label?: string
  predictions_count?: number
  next_round_predictions_count?: number
  last_generated_at?: string | null
  readiness?: string
}

function formatValue(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—'
  return String(v)
}

export function DataHealth() {
  const { selectedCompetition, selectedCompetitionId } = useCompetition()
  const { selectedModelVersion, selectedModelLabel } = useModelSelection()
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoading(true)
    setError(null)
    try {
      setData(
        await getCompetitionDataHealth(selectedCompetitionId, {
          modelVersion: selectedModelVersion,
        }),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selectedCompetitionId, selectedModelVersion])

  useEffect(() => {
    void load()
  }, [load])

  const modelDetails = (data?.predictions_by_model_detail as ModelHealthDetail[] | undefined) ?? []

  const rows: HealthRow[] = data
    ? [
        { label: 'Fixture totali', value: data.fixture_count as number },
        { label: 'Fixture finite', value: data.finished_fixture_count as number },
        { label: 'Squadre', value: data.teams_count as number },
        { label: 'Team stats', value: data.team_stats_count as number },
        { label: 'Profili giocatori', value: data.player_profiles_count as number },
        { label: 'Predictions (totale)', value: data.predictions_count as number },
        { label: 'Modello selezionato', value: selectedModelLabel },
        {
          label: 'Prediction next round (modello selezionato)',
          value: data.selected_model_next_round_predictions_count as number,
        },
        { label: 'Lineups API-Football', value: data.lineup_rows_count as number },
        { label: 'Lineups SportAPI', value: data.sportapi_lineup_rows_count as number },
        { label: 'Formazioni ufficiali (SportAPI)', value: data.confirmed_lineups_count as number },
        { label: 'Formazioni probabili (SportAPI)', value: data.probable_lineups_count as number },
        { label: 'Mapping SportAPI', value: data.sportapi_mappings_count as number },
        { label: 'Coverage lineups (finite)', value: `${data.lineup_coverage_pct ?? '—'}%` },
        { label: 'Prossimo turno — fixture', value: data.next_round_fixture_count as number },
        {
          label: 'Prossimo turno — lineups SportAPI',
          value: (data.next_round_sportapi_lineups_count ?? data.next_round_lineups_count) as number,
        },
        {
          label: 'Prossimo turno — coverage lineups',
          value: `${data.next_round_lineup_coverage_pct ?? '—'}%`,
        },
        { label: 'Prossimo turno — mapping mancanti', value: data.missing_mappings_next_round as number },
        { label: 'Mapping mancanti (finite)', value: data.missing_mappings as number },
      ]
    : []

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">
          Data Health{selectedCompetition ? ` — ${selectedCompetition.name}` : ''}
        </h1>
        <ContextBanner showModelSelector={false} />
      </header>

      {modelDetails.length > 0 ? (
        <section className="rounded-2xl border border-indigo-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-indigo-900">Prediction per modello</h2>
          <ul className="mt-3 space-y-2 text-sm text-slate-700">
            {modelDetails.map((m) => (
              <li key={m.model_version} className="flex flex-wrap gap-x-3 gap-y-1">
                <span className="font-medium text-slate-900">
                  {m.label ?? labelForModelVersion(m.model_version)}:
                </span>
                <span>{m.predictions_count ?? 0} totali</span>
                <span>· next round: {m.next_round_predictions_count ?? 0}</span>
                <span>· readiness: {m.readiness ?? '—'}</span>
                {m.last_generated_at ? (
                  <span className="text-xs text-slate-500">· ultimo refresh: {m.last_generated_at}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">{error}</div>
      ) : null}

      {loading ? <p className="text-sm text-slate-500">Caricamento…</p> : null}

      {!loading && data ? (
        <Card title="Metriche campionato">
          <dl className="grid gap-2 sm:grid-cols-2">
            {rows.map((r) => (
              <div key={r.label} className="rounded-lg border border-slate-100 bg-slate-50/50 px-3 py-2">
                <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{r.label}</dt>
                <dd className="mt-0.5 text-sm font-medium text-slate-900">{formatValue(r.value)}</dd>
              </div>
            ))}
          </dl>
        </Card>
      ) : null}
    </div>
  )
}
