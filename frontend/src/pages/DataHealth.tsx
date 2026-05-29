import { useCallback, useEffect, useState } from 'react'
import { Card } from '../components/ui/Card'
import { CompetitionBadge } from '../components/CompetitionSelector'
import { useCompetition } from '../contexts/CompetitionContext'
import { getCompetitionDataHealth } from '../lib/api'

type HealthRow = { label: string; value: string | number | null | undefined }

function formatValue(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—'
  return String(v)
}

export function DataHealth() {
  const { selectedCompetition, selectedCompetitionId } = useCompetition()
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (selectedCompetitionId == null) return
    setLoading(true)
    setError(null)
    try {
      setData(await getCompetitionDataHealth(selectedCompetitionId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selectedCompetitionId])

  useEffect(() => {
    void load()
  }, [load])

  const rows: HealthRow[] = data
    ? [
        { label: 'Fixture totali', value: data.fixture_count as number },
        { label: 'Fixture finite', value: data.finished_fixture_count as number },
        { label: 'Squadre', value: data.teams_count as number },
        { label: 'Team stats', value: data.team_stats_count as number },
        { label: 'Profili giocatori', value: data.player_profiles_count as number },
        { label: 'Predictions', value: data.predictions_count as number },
        ...(data.predictions_by_model && typeof data.predictions_by_model === 'object'
          ? Object.entries(data.predictions_by_model as Record<string, number>).map(([mv, cnt]) => ({
              label: `Predictions — ${mv}`,
              value: cnt,
            }))
          : []),
        { label: 'Lineups API-Football', value: data.lineup_rows_count as number },
        { label: 'Lineups SportAPI', value: data.sportapi_lineup_rows_count as number },
        { label: 'Formazioni ufficiali (SportAPI)', value: data.confirmed_lineups_count as number },
        { label: 'Formazioni probabili (SportAPI)', value: data.probable_lineups_count as number },
        { label: 'Mapping SportAPI', value: data.sportapi_mappings_count as number },
        { label: 'Coverage lineups (finite)', value: `${data.lineup_coverage_pct ?? '—'}%` },
        {
          label: 'Prossimo turno — fixture',
          value: data.next_round_fixture_count as number,
        },
        {
          label: 'Prossimo turno — lineups SportAPI',
          value: (data.next_round_sportapi_lineups_count ?? data.next_round_lineups_count) as number,
        },
        {
          label: 'Prossimo turno — coverage lineups',
          value: `${data.next_round_lineup_coverage_pct ?? '—'}%`,
        },
        {
          label: 'Prossimo turno — mapping mancanti',
          value: data.missing_mappings_next_round as number,
        },
        { label: 'Mapping mancanti (finite)', value: data.missing_mappings as number },
      ]
    : []

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">
          Data Health{selectedCompetition ? ` — ${selectedCompetition.name}` : ''}
        </h1>
        <CompetitionBadge />
        <p className="mt-1 text-sm text-slate-600">
          Stato del database e delle pipeline per il campionato selezionato.
        </p>
      </header>
      <Card title="Metriche campionato">
        {loading ? <p className="text-sm text-slate-600">Caricamento…</p> : null}
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        {rows.length ? (
          <dl className="grid gap-2 sm:grid-cols-2">
            {rows.map(({ label, value }) => (
              <div key={label} className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2">
                <dt className="text-xs text-slate-500">{label}</dt>
                <dd className="text-sm font-semibold text-slate-900">{formatValue(value)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {data ? (
          <details className="mt-4">
            <summary className="cursor-pointer text-xs text-slate-500">JSON completo</summary>
            <pre className="mt-2 max-h-[320px] overflow-auto rounded bg-slate-50 p-3 text-xs">
              {JSON.stringify(data, null, 2)}
            </pre>
          </details>
        ) : null}
      </Card>
    </div>
  )
}
