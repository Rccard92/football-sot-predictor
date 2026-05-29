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
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-indigo-900">Prediction per modello</h2>
            {data?.model_comparison_available != null ? (
              <span
                className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                  data.model_comparison_available
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                    : 'border-slate-200 bg-slate-50 text-slate-600'
                }`}
              >
                Confronto disponibile: {data.model_comparison_available ? 'sì' : 'no'}
              </span>
            ) : null}
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm text-slate-700">
              <thead>
                <tr className="border-b border-slate-200 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-4">Modello</th>
                  <th className="py-2 pr-4">Totale</th>
                  <th className="py-2 pr-4">Prossimo turno</th>
                  <th className="py-2">Readiness</th>
                </tr>
              </thead>
              <tbody>
                {modelDetails.map((m) => (
                  <tr key={m.model_version} className="border-b border-slate-100">
                    <td className="py-2 pr-4 font-medium text-slate-900">
                      {m.label ?? labelForModelVersion(m.model_version)}
                    </td>
                    <td className="py-2 pr-4 tabular-nums">{m.predictions_count ?? 0}</td>
                    <td className="py-2 pr-4 tabular-nums">{m.next_round_predictions_count ?? 0}</td>
                    <td className="py-2">{m.readiness ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {data?.xg_feed != null ? (
        <section className="rounded-2xl border border-emerald-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-emerald-900">Copertura xG</h2>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {(
              [
                {
                  label: 'xG feed available',
                  value: (data.xg_feed as { xg_feed_available?: boolean }).xg_feed_available ? 'sì' : 'no',
                },
                {
                  label: 'Righe con xG effettivo',
                  value: (data.xg_feed as { rows_with_effective_xg?: number }).rows_with_effective_xg,
                },
                {
                  label: 'Copertura effettiva',
                  value: `${(data.xg_feed as { effective_coverage_pct?: number }).effective_coverage_pct ?? '—'}%`,
                },
                {
                  label: 'Baseline xG lega (for)',
                  value: (data.xg_feed as { league_baseline_xg_for?: number }).league_baseline_xg_for,
                },
                {
                  label: 'Verdict',
                  value: (data.xg_feed as { verdict?: string }).verdict,
                },
                {
                  label: 'Source path',
                  value: (data.xg_feed as { source_path?: string }).source_path,
                },
              ] as HealthRow[]
            ).map((r) => (
              <div key={r.label} className="rounded-lg border border-slate-100 bg-slate-50/50 px-3 py-2">
                <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{r.label}</dt>
                <dd className="mt-0.5 text-sm font-medium text-slate-900">{formatValue(r.value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {data?.v21_variable_coverage != null ? (
        <section className="rounded-2xl border border-violet-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-violet-900">Copertura variabili v2.1 (prossimo turno)</h2>
          <p className="mt-1 text-xs text-slate-600">
            xG nel feed:{' '}
            {(data.xg_feed as { xg_feed_available?: boolean } | undefined)?.xg_feed_available ? 'sì' : 'no'}
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-xs text-slate-700">
              <thead>
                <tr className="border-b border-slate-200 text-[10px] font-semibold uppercase text-slate-500">
                  <th className="py-2 pr-3">Macroarea</th>
                  <th className="py-2 pr-3">Tot</th>
                  <th className="py-2 pr-3">Disp.</th>
                  <th className="py-2 pr-3">Deriv.</th>
                  <th className="py-2 pr-3">Missing</th>
                  <th className="py-2">N/T</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(
                  ((data.v21_variable_coverage as { by_macro?: Record<string, Record<string, number>> })
                    ?.by_macro ?? {}) as Record<string, Record<string, number>>,
                ).map(([key, bucket]) => (
                  <tr key={key} className="border-b border-slate-100">
                    <td className="py-2 pr-3 font-medium">{key}</td>
                    <td className="py-2 pr-3 tabular-nums">{bucket.total ?? 0}</td>
                    <td className="py-2 pr-3 tabular-nums">{bucket.available ?? 0}</td>
                    <td className="py-2 pr-3 tabular-nums">{bucket.available_derived ?? 0}</td>
                    <td className="py-2 pr-3 tabular-nums">{bucket.missing ?? 0}</td>
                    <td className="py-2 tabular-nums">{bucket.not_tracked_yet ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
