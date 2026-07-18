import { useEffect, useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { CecchinoStatusMessage } from '../components/cecchino/CecchinoStatusMessage'
import { useCecchinoGoalIntensityV5Audit } from '../hooks/useCecchinoGoalIntensityV5Audit'
import { useCecchinoGoalIntensityV5CandidateIndices } from '../hooks/useCecchinoGoalIntensityV5CandidateIndices'
import { useCecchinoGoalIntensityV5Dataset } from '../hooks/useCecchinoGoalIntensityV5Dataset'
import { useCecchinoGoalIntensityV5Statistics } from '../hooks/useCecchinoGoalIntensityV5Statistics'
import {
  buildGoalIntensityAuditJsonFilename,
  buildGoalIntensityFeatureInventoryCsvFilename,
  buildGoalIntensityFixtureAuditCsvFilename,
  classifyGoalIntensityFetchError,
  featureInventoryToCsv,
  fetchGoalIntensityV5Availability,
  fixtureAuditToCsv,
  isGoalIntensityAuditDegraded,
  isGoalIntensityAuditUnusable,
  postGoalIntensityV5CandidateIndicesExport,
  postGoalIntensityV5DatasetExport,
  postGoalIntensityV5StatisticsExport,
  type GoalIntensityCandidateIndicesExportKind,
  type GoalIntensityDatasetExportKind,
  type GoalIntensityDatasetRow,
  type GoalIntensityFixtureAuditRow,
  type GoalIntensityV5AuditResponse,
  type GoalIntensityV5AvailabilityResponse,
  type GoalIntensityV5CandidateIndicesResponse,
  type GoalIntensityV5DatasetResponse,
  type GoalIntensityV5StatisticsResponse,
  type GoalIntensityStatisticsExportKind,
} from '../lib/cecchinoGoalIntensityV5ResearchApi'
import { downloadJsonFile, downloadTextFile } from '../lib/downloadJsonFile'
import { isoDaysAgoLocal, todayLocalIso } from '../utils/dateLocal'
import { formatFetchError } from '../utils/formatFetchError'

type LabTab = 'audit' | 'dataset' | 'statistics' | 'indices'

const PILLAR_LABELS: Record<string, string> = {
  offensive_production: 'Produzione offensiva',
  defensive_solidity: 'Solidità difensiva',
  match_tempo: 'Ritmo della partita',
  offensive_stability: 'Stabilità offensiva',
}

type XgFilter = 'all' | 'available' | 'partial' | 'missing' | 'excluded_unsafe'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
      <div className="mt-3 text-sm text-slate-700">{children}</div>
    </section>
  )
}

function Kv({ label, value }: { label: string; value: unknown }) {
  const text = value == null || value === '' ? '—' : String(value)
  return (
    <div className="flex justify-between gap-3 border-b border-slate-100 py-1 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className="tabular-nums font-medium text-slate-800">{text}</span>
    </div>
  )
}

function JsonBlock({ data }: { data: unknown }) {
  if (data == null) {
    return <p className="text-xs text-slate-500">Dato non disponibile.</p>
  }
  return (
    <pre className="max-h-80 overflow-auto rounded-lg bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-700">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

function XgStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; className: string }> = {
    available: {
      label: 'xG presente',
      className: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    },
    partial: {
      label: 'xG parziale',
      className: 'bg-sky-50 text-sky-800 border-sky-200',
    },
    missing: {
      label: 'xG non disponibile',
      className: 'bg-slate-100 text-slate-700 border-slate-200',
    },
    excluded_unsafe: {
      label: 'xG escluso',
      className: 'bg-red-50 text-red-800 border-red-200',
    },
  }
  const cfg = map[status] ?? {
    label: status || '—',
    className: 'bg-slate-100 text-slate-600 border-slate-200',
  }
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${cfg.className}`}
    >
      {cfg.label}
    </span>
  )
}

function filterFixtureRows(
  rows: GoalIntensityFixtureAuditRow[],
  xgFilter: XgFilter,
  competitionFilter: string,
): GoalIntensityFixtureAuditRow[] {
  const compTrim = competitionFilter.trim()
  const compId = compTrim === '' ? null : Number(compTrim)
  return rows.filter((row) => {
    if (xgFilter !== 'all' && row.xg_status !== xgFilter) return false
    if (compId != null && !Number.isNaN(compId) && row.competition_id !== compId) return false
    return true
  })
}

function AuditBody({ audit }: { audit: GoalIntensityV5AuditResponse }) {
  const [xgFilter, setXgFilter] = useState<XgFilter>('all')
  const [rowCompetitionId, setRowCompetitionId] = useState('')

  const summary = audit.dataset_summary ?? {}
  const v4 = audit.current_v4_inventory ?? {}
  const anti = audit.anti_leakage ?? {}
  const rec = audit.implementation_recommendation ?? {}
  const unusable = isGoalIntensityAuditUnusable(audit)
  const degraded = isGoalIntensityAuditDegraded(audit)
  const temporal = (summary.temporal_distribution ?? {}) as Record<string, unknown>
  const exclusionReasons = audit.exclusion_reasons ?? {}
  const debugSamples = audit.debug_samples ?? {}
  const xgCohorts = (summary.xg_cohorts ?? {}) as Record<string, unknown>
  const xgReadiness = (summary.xg_value_research_readiness ?? {}) as Record<string, unknown>
  const xgSourcesSafe =
    (anti.xg_sources_feature_safe as Record<string, number> | undefined) ??
    (anti.xg_source_feature_safe as Record<string, number> | undefined) ??
    {}
  const fixtureRows = audit.fixture_audit_rows ?? []
  const filteredRows = filterFixtureRows(fixtureRows, xgFilter, rowCompetitionId)

  return (
    <div className="space-y-4">
      {unusable ? (
        <p
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm font-medium text-red-950"
        >
          Audit non utilizzabile (quality=unusable
          {summary.feature_safe_rate_pct != null
            ? `; feature-safe ${String(summary.feature_safe_rate_pct)}%`
            : ''}
          ): correggere la pipeline dati prima della Fase 1B.
        </p>
      ) : null}
      {!unusable && degraded ? (
        <p
          role="status"
          className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950"
        >
          Audit degradato (quality=degraded
          {summary.feature_safe_rate_pct != null
            ? `; feature-safe ${String(summary.feature_safe_rate_pct)}%`
            : ''}
          ): risultati parziali, usare con cautela.
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50"
          onClick={() =>
            downloadJsonFile(
              buildGoalIntensityAuditJsonFilename(audit.filters.date_from, audit.filters.date_to),
              audit,
            )
          }
        >
          Scarica JSON audit completo
        </button>
        <button
          type="button"
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50"
          onClick={() =>
            downloadTextFile(
              buildGoalIntensityFeatureInventoryCsvFilename(
                audit.filters.date_from,
                audit.filters.date_to,
              ),
              featureInventoryToCsv(audit.feature_inventory ?? []),
              'text/csv;charset=utf-8',
            )
          }
        >
          Scarica CSV inventario feature
        </button>
        <button
          type="button"
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50"
          onClick={() =>
            downloadTextFile(
              buildGoalIntensityFixtureAuditCsvFilename(
                audit.filters.date_from,
                audit.filters.date_to,
              ),
              fixtureAuditToCsv(filteredRows),
              'text/csv;charset=utf-8',
            )
          }
        >
          Scarica CSV Fixture audit
        </button>
      </div>

      <Section title="1. Stato modulo v4">
        <Kv label="Ruolo" value={v4.role} />
        <Kv label="Versione" value={v4.version} />
        <Kv label="Metodo" value={v4.method} />
        <Kv label="Grandezza" value={v4.primary_quantity} />
        <Kv label="Soglie" value={JSON.stringify(v4.classification_thresholds)} />
        <p className="mt-2 text-xs text-slate-600">
          Conservato come legacy_reference. Nessuna modifica produttiva in Fase 1A.
        </p>
      </Section>

      <Section title="2. Copertura dataset (Fixture kickoff)">
        <Kv label="Fixture locali raw" value={summary.local_fixtures_raw ?? summary.rows_raw} />
        <Kv label="Fixture locali deduped" value={summary.local_fixtures_deduped ?? summary.rows_deduped} />
        <Kv label="Duplicati rimossi" value={summary.duplicates_removed} />
        <Kv label="Snapshot Today associati" value={summary.today_snapshots_matched} />
        <Kv label="Snapshot Today mancanti" value={summary.today_snapshots_missing} />
        <Kv label="Righe feature-safe" value={summary.row_feature_safe ?? summary.leakage_safe_rows} />
        <Kv label="Feature-safe rate %" value={summary.feature_safe_rate_pct} />
        <Kv label="Audit quality" value={summary.audit_quality} />
        <Kv label="Targets FT" value={summary.targets_all_finished} />
        <Kv label="Targets feature-safe" value={summary.targets_feature_safe} />
        <Kv label="Competizioni" value={summary.competitions} />
        <Kv label="Paesi" value={summary.countries} />
        <Kv label="Sample size medio" value={summary.sample_size_mean} />
        <Kv label="Audit usable" value={summary.audit_usable ? 'sì' : 'no'} />
        <Kv label="Coorte" value={summary.cohort_basis} />
        <div className="mt-2">
          <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-slate-400">
            Distribuzione mensile (kickoff)
          </p>
          <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(temporal).map(([month, val]) => {
              const block = val as { count?: number; note?: string }
              return (
                <div key={month} className="rounded border border-slate-100 px-2 py-1 text-xs">
                  <span className="font-medium text-slate-800">{month}</span>
                  <span className="ml-2 tabular-nums text-slate-600">{block.count ?? 0}</span>
                  {block.note ? (
                    <span className="ml-2 text-[10px] text-amber-700">{block.note}</span>
                  ) : null}
                </div>
              )
            })}
          </div>
        </div>
      </Section>

      <Section title="3. Copertura xG">
        <div className="mb-3 flex flex-wrap gap-2">
          <XgStatusBadge status="available" />
          <XgStatusBadge status="partial" />
          <XgStatusBadge status="missing" />
          <XgStatusBadge status="excluded_unsafe" />
        </div>
        <Kv label="Fixture feature-safe" value={xgCohorts.all_feature_safe} />
        <Kv label="xG presente" value={xgCohorts.xg_available} />
        <Kv label="xG presente %" value={xgCohorts.xg_available_pct} />
        <Kv label="xG parziale" value={xgCohorts.xg_partial} />
        <Kv label="xG parziale %" value={xgCohorts.xg_partial_pct} />
        <Kv label="xG non disponibile" value={xgCohorts.xg_missing} />
        <Kv label="xG non disponibile %" value={xgCohorts.xg_missing_pct} />
        <Kv label="xG escluso (qualità)" value={xgCohorts.xg_excluded_unsafe} />
        <Kv label="xG escluso %" value={xgCohorts.xg_excluded_unsafe_pct} />
        <p className="mb-1 mt-3 text-[11px] font-medium uppercase tracking-wide text-slate-400">
          Sorgenti xG (feature-safe)
        </p>
        <div className="grid gap-1 sm:grid-cols-2">
          {Object.entries(xgSourcesSafe).map(([src, n]) => (
            <Kv key={src} label={src} value={n} />
          ))}
        </div>
        <p className="mb-1 mt-3 text-[11px] font-medium uppercase tracking-wide text-slate-400">
          Readiness confronto paired
        </p>
        <Kv label="Paired possibile" value={xgReadiness.paired_comparison_possible ? 'sì' : 'no'} />
        <Kv label="Paired fixture count" value={xgReadiness.paired_fixture_count} />
        <Kv
          label="Sample minimo (≥50)"
          value={xgReadiness.minimum_recommended_sample_reached ? 'raggiunto' : 'non raggiunto'}
        />
        {xgReadiness.note ? (
          <p className="mt-2 text-xs text-slate-600">{String(xgReadiness.note)}</p>
        ) : null}
      </Section>

      <Section title="4. Copertura dei quattro pilastri">
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(audit.pillar_coverage ?? {}).map(([key, block]) => (
            <div key={key} className="rounded-lg border border-slate-100 bg-slate-50/80 p-3">
              <h3 className="text-xs font-semibold text-slate-900">
                {PILLAR_LABELS[key] ?? key}
              </h3>
              <Kv label="Totali" value={block.fixtures_total} />
              <Kv label="Con almeno una feature" value={block.fixtures_with_any_feature} />
              <Kv label="Tutte le primarie" value={block.fixtures_with_all_primary} />
              <Kv label="Copertura completa %" value={block.coverage_complete_pct} />
              <Kv label="Sample size medio" value={block.sample_size_mean} />
              {key === 'defensive_solidity' &&
              Array.isArray(block.primary_feature_keys) &&
              block.primary_feature_keys.length === 0 ? (
                <p className="mt-2 text-xs text-slate-600">
                  Feature difensive disponibili; nessuna feature primaria ancora selezionata
                  statisticamente.
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </Section>

      <Section title="5. Inventario variabili">
        {!audit.feature_inventory?.length ? (
          <p className="text-xs text-slate-500">Nessuna feature nel periodo.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Feature</th>
                  <th className="py-1 pr-2">Pilastro</th>
                  <th className="py-1 pr-2">Coverage %</th>
                  <th className="py-1 pr-2">Mean</th>
                  <th className="py-1 pr-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {audit.feature_inventory.map((f) => (
                  <tr key={f.feature_key} className="border-t border-slate-100">
                    <td className="py-1.5 pr-2 font-medium text-slate-800">{f.feature_key}</td>
                    <td className="py-1.5 pr-2">{PILLAR_LABELS[f.pillar] ?? f.pillar}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{f.coverage_pct}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{f.mean ?? '—'}</td>
                    <td className="py-1.5 pr-2">{f.recommended_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="6. Fixture audit">
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-600">
            Stato xG
            <select
              className="mt-1 block rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs"
              value={xgFilter}
              onChange={(e) => setXgFilter(e.target.value as XgFilter)}
            >
              <option value="all">Tutte</option>
              <option value="available">Con xG completo</option>
              <option value="partial">Con xG parziale</option>
              <option value="missing">Senza xG</option>
              <option value="excluded_unsafe">xG escluso</option>
            </select>
          </label>
          <label className="text-xs text-slate-600">
            Competition ID
            <input
              type="text"
              inputMode="numeric"
              placeholder="opzionale"
              className="mt-1 block w-28 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs"
              value={rowCompetitionId}
              onChange={(e) => setRowCompetitionId(e.target.value)}
            />
          </label>
          <p className="text-[11px] text-slate-500">
            Filtri client-side ({filteredRows.length}/{fixtureRows.length} righe). Nessun re-POST.
          </p>
        </div>
        {!filteredRows.length ? (
          <p className="text-xs text-slate-500">Nessuna riga con i filtri correnti.</p>
        ) : (
          <div className="max-h-96 overflow-auto">
            <table className="min-w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-white text-slate-500">
                <tr>
                  <th className="py-1 pr-2">ID</th>
                  <th className="py-1 pr-2">Comp</th>
                  <th className="py-1 pr-2">Kickoff</th>
                  <th className="py-1 pr-2">Partita</th>
                  <th className="py-1 pr-2">Safe</th>
                  <th className="py-1 pr-2">xG</th>
                  <th className="py-1 pr-2">Source</th>
                  <th className="py-1 pr-2">Goals</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => (
                  <tr key={row.local_fixture_id} className="border-t border-slate-100">
                    <td className="py-1 pr-2 tabular-nums">{row.local_fixture_id}</td>
                    <td className="py-1 pr-2 tabular-nums">{row.competition_id ?? '—'}</td>
                    <td className="py-1 pr-2 whitespace-nowrap">{row.kickoff ?? '—'}</td>
                    <td className="py-1 pr-2">
                      {row.home_team ?? '?'} – {row.away_team ?? '?'}
                    </td>
                    <td className="py-1 pr-2">{row.row_feature_safe ? 'sì' : 'no'}</td>
                    <td className="py-1 pr-2">
                      <XgStatusBadge status={String(row.xg_status)} />
                    </td>
                    <td className="py-1 pr-2">{row.xg_source}</td>
                    <td className="py-1 pr-2 tabular-nums">{row.target_total_goals_ft ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="7. Variabili escluse">
        <JsonBlock data={audit.excluded_advanced_features} />
      </Section>

      <Section title="8. Anti-leakage e identity">
        <Kv label="Checked" value={anti.rows_checked} />
        <Kv label="Feature-safe / passed" value={anti.row_feature_safe ?? anti.rows_passed} />
        <Kv label="Failed" value={anti.rows_failed} />
        <Kv label="Identity verificata" value={anti.identity_verified} />
        <Kv label="Identity non disponibile" value={anti.identity_not_available} />
        <Kv label="Identity fallita" value={anti.identity_failed} />
        <Kv label="Identity check errors" value={anti.identity_check_errors} />
        <Kv label="Identity mismatch" value={anti.fixture_identity_mismatch} />
        <Kv label="Cutoff mismatch (diagnostica)" value={anti.cutoff_mismatch} />
        <Kv label="xG available" value={anti.xg_available} />
        <Kv label="xG partial" value={anti.xg_partial} />
        <Kv label="xG da snapshot" value={anti.xg_from_today_snapshot} />
        <Kv label="xG da FixtureTeamStat" value={anti.xg_from_fixture_team_stats} />
        <Kv label="xG missing" value={anti.xg_missing} />
        <Kv label="xG excluded_unsafe" value={anti.xg_excluded_unsafe} />
      </Section>

      <Section title="9. Motivi di esclusione ed esempi">
        <JsonBlock data={exclusionReasons} />
        <p className="mb-1 mt-3 text-[11px] font-medium uppercase tracking-wide text-slate-400">
          Esempi diagnostici (max 20 / motivo)
        </p>
        <JsonBlock data={debugSamples} />
      </Section>

      <Section title="10. Disponibilità API/DB">
        <JsonBlock data={audit.api_availability} />
      </Section>

      <Section title="11. Dipendenze e conflitti">
        <JsonBlock data={audit.legacy_dependencies} />
        <p className="mb-2 mt-3 text-xs font-medium text-slate-500">Conflitti</p>
        <JsonBlock data={audit.potential_conflicts} />
      </Section>

      <Section title="12. Piano consigliato per Fase 1B">
        <JsonBlock data={rec} />
      </Section>

      <Section title="13. Warning">
        {(audit.warnings ?? []).length === 0 ? (
          <p className="text-xs text-slate-500">Nessun warning.</p>
        ) : (
          <ul className="list-disc space-y-1 pl-5 text-xs text-amber-900">
            {audit.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[11px] text-slate-400">
          Performance: {JSON.stringify(audit.performance ?? {})}
        </p>
      </Section>
    </div>
  )
}

function DatasetBody({
  dataset,
  onExport,
  exportBusy,
  exportError,
}: {
  dataset: GoalIntensityV5DatasetResponse
  onExport: (kind: GoalIntensityDatasetExportKind) => void
  exportBusy: boolean
  exportError: string | null
}) {
  const summary = dataset.dataset_summary ?? {}
  const dedupe = dataset.deduplication ?? {}
  const history = dataset.history_quality ?? {}
  const xg = dataset.xg_cohorts ?? {}
  const paired = dataset.paired_xg_readiness ?? {}
  const identity = dataset.identity_diagnostics ?? {}
  const bias = dataset.exclusion_bias_report ?? {}
  const cohortCounts = (summary.cohort_counts ?? {}) as Record<string, number>
  const preview = dataset.dataset_preview_rows ?? []
  const elig = dataset.eligibility_diagnostics ?? {}
  const cohortBasis = String(dataset.cohort_basis ?? summary.cohort_basis ?? '')
  const unknownCount = Number(elig.today_eligibility_unknown ?? 0)
  const hasIneligibleRows = (preview as GoalIntensityDatasetRow[]).some(
    (r) => r.eligibility_status != null && String(r.eligibility_status) !== 'eligible',
  )
  const badScanDate = (preview as GoalIntensityDatasetRow[]).some((r) => {
    const sd = r.scan_date
    return typeof sd === 'string' && sd < '2026-06-19'
  })
  const blocking =
    unknownCount > 0 ||
    hasIneligibleRows ||
    (cohortBasis !== '' && cohortBasis !== 'cecchino_today_eligible_scan_date') ||
    badScanDate ||
    dataset.status === 'error'

  return (
    <div className="space-y-4">
      <p className="text-sm font-medium text-slate-800">
        Coorte research: solo partite eleggibili Cecchino Today.
      </p>
      {blocking ? (
        <CecchinoStatusMessage
          variant="error"
          title="Coorte non valida"
          message={
            dataset.error ||
            (unknownCount > 0
              ? `Eleggibilità sconosciuta: ${unknownCount} partite (fail-closed).`
              : hasIneligibleRows
                ? 'Il dataset contiene righe non eleggibili.'
                : badScanDate
                  ? 'Esistono target con scan_date precedente al 19/06/2026.'
                  : cohortBasis !== 'cecchino_today_eligible_scan_date'
                    ? `cohort_basis non valido: ${cohortBasis || 'mancante'}`
                    : 'Errore di coorte.')
          }
        />
      ) : null
      }
      <div className="flex flex-wrap gap-2">
        {(
          [
            ['all', 'CSV dataset completo'],
            ['core_min5', 'CSV core ≥5'],
            ['core_min10', 'CSV core ≥10'],
            ['xg_paired', 'CSV paired xG'],
            ['ineligible_diagnostics', 'CSV non eleggibili (diagnostica)'],
            ['summary', 'JSON summary'],
          ] as const
        ).map(([kind, label]) => (
          <button
            key={kind}
            type="button"
            disabled={exportBusy}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => onExport(kind)}
          >
            {label}
          </button>
        ))}
      </div>
      {exportError ? (
        <CecchinoStatusMessage variant="error" title="Errore export" message={exportError} />
      ) : null}
      {exportBusy ? (
        <p className="text-xs text-slate-500">Export in corso dal backend…</p>
      ) : null}

      <Section title="Diagnostica eleggibilità Cecchino Today">
        <Kv label="Scansioni Today raw" value={elig.today_rows_raw} />
        <Kv label="Partite uniche" value={elig.today_unique_matches} />
        <Kv label="Eleggibili" value={elig.today_eligible_matches} />
        <Kv label="Non eleggibili" value={elig.today_ineligible_matches} />
        <Kv label="Eleggibilità sconosciuta" value={elig.today_eligibility_unknown} />
        <Kv label="Eleggibili concluse" value={elig.eligible_finished_matches} />
        <Kv label="Eleggibili pending" value={elig.eligible_pending_matches} />
        <Kv label="Eleggibili non risolte" value={elig.eligible_unresolved_matches} />
        <Kv label="Eleggibili feature-safe" value={elig.eligible_feature_safe_matches} />
        <Kv label="Eleggibili escluse identity" value={elig.eligible_identity_excluded_matches} />
        <p className="mb-1 mt-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">
          Motivi non eleggibilità
        </p>
        <JsonBlock data={elig.ineligible_by_reason} />
      </Section>

      <Section title="Riepilogo dataset">
        <Kv label="Versione" value={dataset.version} />
        <Kv label="Righe iniziali" value={summary.rows_initial} />
        <Kv label="Dopo dedupe" value={summary.rows_after_composite_dedupe} />
        <Kv label="Righe feature-safe" value={summary.rows_feature_safe} />
        <Kv label="Identity excluded" value={summary.rows_identity_excluded} />
        <Kv label="v4 invariata" value={summary.v4_unchanged ? 'sì' : 'no'} />
        <Kv label="Nessuna formula v5" value={summary.no_v5_formula ? 'sì' : 'no'} />
      </Section>

      <Section title="Deduplicazione">
        <Kv label="Duplicati provider rimossi" value={dedupe.duplicates_provider_removed} />
        <Kv label="Duplicati compositi rimossi" value={dedupe.duplicates_composite_removed} />
        <Kv label="Dopo provider" value={dedupe.rows_after_provider} />
        <Kv label="Dopo composita" value={dedupe.rows_after_composite} />
        <Kv label="Gruppi duplicati" value={dedupe.duplicate_groups_count} />
      </Section>

      <Section title="History quality">
        <Kv label="none" value={history.none} />
        <Kv label="very_low" value={history.very_low} />
        <Kv label="low" value={history.low} />
        <Kv label="standard" value={history.standard} />
        <Kv label="robust" value={history.robust} />
        <Kv label="history_any (≥1)" value={history.history_any} />
        <Kv label="history_min_5" value={history.history_min_5} />
        <Kv label="history_min_10" value={history.history_min_10} />
        <Kv label="history_min_20" value={history.history_min_20} />
      </Section>

      <Section title="Coorti core / xG">
        <Kv label="all_feature_safe" value={cohortCounts.all_feature_safe} />
        <Kv label="core_history_any" value={cohortCounts.core_history_any} />
        <Kv label="core_history_min_5" value={cohortCounts.core_history_min_5} />
        <Kv label="core_history_min_10" value={cohortCounts.core_history_min_10} />
        <Kv label="core_history_min_20" value={cohortCounts.core_history_min_20} />
        <Kv label="xg_complete_paired" value={cohortCounts.xg_complete_paired} />
        <Kv label="xg_partial_diagnostic" value={cohortCounts.xg_partial_diagnostic} />
        <Kv label="xG available" value={xg.xg_available} />
        <Kv label="xG partial" value={xg.xg_partial} />
        <Kv label="xG missing" value={xg.xg_missing} />
        <Kv label="Paired fixture count" value={paired.paired_fixture_count} />
        <Kv label="Sample minimo paired (≥50)" value={paired.minimum_recommended_sample_reached ? 'sì' : 'no'} />
        <Kv label="fixture_ids_hash" value={paired.fixture_ids_hash} />
      </Section>

      <Section title="Identity failure (aggregati)">
        <Kv label="Escluse" value={identity.identity_excluded_count} />
        <p className="mb-1 mt-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">
          Per motivo
        </p>
        <JsonBlock data={identity.by_reason} />
      </Section>

      <Section title="Exclusion bias (diagnostica)">
        <JsonBlock data={bias} />
      </Section>

      <Section title="Anteprima righe">
        <p className="mb-2 text-xs text-slate-600">
          Anteprima limitata a 100 righe. Gli export completi vengono generati dal backend.
        </p>
        {!preview.length ? (
          <p className="text-xs text-slate-500">Nessuna riga in anteprima.</p>
        ) : (
          <div className="max-h-72 overflow-auto">
            <table className="min-w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-white text-slate-500">
                <tr>
                  <th className="py-1 pr-2">ID</th>
                  <th className="py-1 pr-2">Kickoff</th>
                  <th className="py-1 pr-2">Sample</th>
                  <th className="py-1 pr-2">Tier</th>
                  <th className="py-1 pr-2">xG</th>
                  <th className="py-1 pr-2">Goals</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((row) => (
                  <tr key={String(row.local_fixture_id)} className="border-t border-slate-100">
                    <td className="py-1 pr-2 tabular-nums">{String(row.local_fixture_id)}</td>
                    <td className="py-1 pr-2 whitespace-nowrap">{String(row.kickoff ?? '—')}</td>
                    <td className="py-1 pr-2 tabular-nums">{String(row.sample_size ?? '—')}</td>
                    <td className="py-1 pr-2">{String(row.history_quality_tier ?? '—')}</td>
                    <td className="py-1 pr-2">{String(row.xg_status ?? '—')}</td>
                    <td className="py-1 pr-2 tabular-nums">{String(row.total_goals_ft ?? '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Performance">
        <JsonBlock data={dataset.performance} />
      </Section>

      <Section title="Warning">
        {(dataset.warnings ?? []).length === 0 ? (
          <p className="text-xs text-slate-500">Nessun warning.</p>
        ) : (
          <ul className="list-disc space-y-1 pl-5 text-xs text-amber-900">
            {dataset.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}

const STATISTICS_EXPORTS: ReadonlyArray<[GoalIntensityStatisticsExportKind, string]> = [
  ['summary', 'JSON riepilogo'],
  ['feature_signal', 'CSV segnali feature'],
  ['redundancy_matrix', 'CSV matrice ridondanza'],
  ['redundancy_clusters', 'CSV cluster ridondanza'],
  ['temporal_stability', 'CSV stabilità temporale'],
  ['rolling_comparison', 'CSV confronto finestre'],
  ['stability_metrics', 'CSV metriche stabilità'],
  ['xg_value', 'CSV valore xG'],
  ['feature_recommendations', 'CSV raccomandazioni feature'],
]

function RecommendationBadge({ recommendation }: { recommendation: unknown }) {
  const map: Record<string, { label: string; className: string }> = {
    candidate_core: { label: 'Core candidate', className: 'border-emerald-200 bg-emerald-50 text-emerald-800' },
    candidate_secondary: { label: 'Secondary candidate', className: 'border-sky-200 bg-sky-50 text-sky-800' },
    candidate_optional_xg: { label: 'Optional xG', className: 'border-violet-200 bg-violet-50 text-violet-800' },
    redundant_candidate: { label: 'Redundant', className: 'border-amber-200 bg-amber-50 text-amber-800' },
    unstable_candidate: { label: 'Unstable', className: 'border-red-200 bg-red-50 text-red-800' },
    insufficient_evidence: { label: 'Insufficient evidence', className: 'border-slate-200 bg-slate-100 text-slate-700' },
  }
  const cfg = map[String(recommendation)] ?? {
    label: String(recommendation ?? '—'),
    className: 'border-slate-200 bg-slate-100 text-slate-700',
  }
  return (
    <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-medium ${cfg.className}`}>
      {cfg.label}
    </span>
  )
}

function StatisticsBody({
  statistics,
  onExport,
  exportBusy,
  exportError,
}: {
  statistics: GoalIntensityV5StatisticsResponse
  onExport: (kind: GoalIntensityStatisticsExportKind) => void
  exportBusy: boolean
  exportError: string | null
}) {
  const limitations = statistics.research_limitations ?? {}
  const cohort = statistics.cohort_summary ?? {}
  const targets = statistics.target_summary ?? {}
  const signals = statistics.feature_signal_summary ?? []
  const xgSignals = statistics.xg_univariate_summary ?? []
  const redundancy = statistics.redundancy_summary ?? {}
  const rolling = statistics.rolling_window_comparison ?? {}
  const stability = statistics.stability_metric_comparison ?? {}
  const temporal = statistics.temporal_stability_summary ?? {}
  const xg = statistics.xg_value_summary ?? {}
  const recommendations = statistics.feature_recommendations ?? []
  const pillarRecommendations = statistics.pillar_recommendations ?? {}
  const readiness = statistics.phase_1d_readiness ?? {}
  const performance = statistics.performance ?? {}
  const deps = (redundancy.dependencies ?? {}) as Record<string, Record<string, unknown>>
  const exactDuplicates = Object.entries(deps).filter(([, d]) => d.dependency_type === 'exact_duplicate')
  const derived = Object.entries(deps).filter(
    ([, d]) => d.dependency_type === 'derived_linear' || d.dependency_type === 'derived_aggregate',
  )
  const clusterMeta = (redundancy.cluster_meta ?? {}) as Record<string, Record<string, unknown>>
  const representatives = Object.entries(clusterMeta).filter(([, m]) => m.representative_of_cluster)
  const rankingKeys = [
    ['ranking_total_goals_ft', 'Goal totali'],
    ['ranking_goals_ge_2', 'Goal ≥2'],
    ['ranking_goals_ge_3', 'Goal ≥3'],
    ['ranking_btts_ft', 'BTTS'],
  ] as const
  const readinessFlags = [
    'rolling_window_decision_available',
    'stability_metric_decision_available',
    'target_specific_analysis_complete',
    'xg_univariate_analysis_complete',
    'redundancy_representatives_selected',
    'recommendation_consistency_verified',
    'dependency_consistency_verified',
    'pillar_recommendations_consistent',
    'rolling_selection_consistent',
    'stability_recommendations_consistent',
  ] as const
  const readyFor1d =
    readiness.recommended_next_step === 'phase_1d_candidate_indices' &&
    readinessFlags.every((key) => readiness[key] === true)

  const topByTarget = (key: (typeof rankingKeys)[number][0]) =>
    [...recommendations]
      .filter((r) => !String(r.feature_key ?? '').includes('xg'))
      .sort((a, b) => Number(b[key] ?? 0) - Number(a[key] ?? 0))
      .slice(0, 5)

  return (
    <div className="space-y-4">
      <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
        Coorte legacy pre UTC fix: le esclusioni tecniche storiche non sono state rivalutate.
      </p>
      <div className="flex flex-wrap gap-2">
        {STATISTICS_EXPORTS.map(([kind, label]) => (
          <button
            key={kind}
            type="button"
            disabled={exportBusy}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => onExport(kind)}
          >
            {label}
          </button>
        ))}
      </div>
      {exportError ? <CecchinoStatusMessage variant="error" title="Errore export" message={exportError} /> : null}
      {exportBusy ? <p className="text-xs text-slate-500">Export in corso dal backend…</p> : null}

      <Section title="Limiti della ricerca">
        <Kv label="Versione motore eleggibilità" value={limitations.eligibility_engine_version} />
        <Kv label="Riclassificazione UTC storica" value={limitations.utc_historical_exclusions_not_reclassified ? 'non eseguita' : '—'} />
        <Kv label="Backfill" value={limitations.no_backfill ? 'non eseguito' : '—'} />
        {limitations.note ? <p className="mt-2 text-xs text-slate-600">{String(limitations.note)}</p> : null}
      </Section>

      <Section title="Riepilogo coorte">
        {Object.entries(cohort).map(([label, value]) => <Kv key={label} label={label} value={value} />)}
      </Section>

      <Section title="Riepilogo target">
        <JsonBlock data={targets} />
      </Section>

      <Section title="Feature signal (4 target)">
        {!signals.length ? (
          <p className="text-xs text-slate-500">Nessun segnale disponibile.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Feature</th>
                  <th className="py-1 pr-2">Pilastro</th>
                  <th className="py-1 pr-2">Spearman TG</th>
                  <th className="py-1 pr-2">AUC ≥2</th>
                  <th className="py-1 pr-2">AUC ≥3</th>
                  <th className="py-1 pr-2">AUC BTTS</th>
                  <th className="py-1 pr-2">Monotonia</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((feature) => (
                  <tr key={String(feature.feature_key)} className="border-t border-slate-100">
                    <td className="py-1.5 pr-2 font-medium text-slate-800">{String(feature.feature_key ?? '—')}</td>
                    <td className="py-1.5 pr-2">{PILLAR_LABELS[String(feature.pillar)] ?? String(feature.pillar ?? '—')}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{String(feature.spearman_total_goals ?? feature.total_goals_ft_spearman ?? '—')}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{String(feature.auc_goals_ge_2 ?? feature.goals_ge_2_auc ?? '—')}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{String(feature.auc_goals_ge_3 ?? feature.goals_ge_3_auc ?? '—')}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{String(feature.auc_btts_ft ?? feature.btts_ft_auc ?? '—')}</td>
                    <td className="py-1.5 pr-2">{String(feature.monotonic_direction ?? '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Ranking per target">
        <div className="grid gap-3 md:grid-cols-2">
          {rankingKeys.map(([key, label]) => (
            <div key={key} className="rounded-lg border border-slate-100 bg-slate-50/80 p-3">
              <h3 className="mb-2 text-xs font-semibold text-slate-900">{label}</h3>
              <ol className="space-y-1 text-xs text-slate-700">
                {topByTarget(key).map((item, index) => (
                  <li key={`${key}-${String(item.feature_key)}`}>
                    {index + 1}. {String(item.feature_key)} ({String(item[key] ?? '—')})
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      </Section>

      <Section title="xG univariata (paired)">
        {!xgSignals.length ? (
          <p className="text-xs text-slate-500">Nessuna metrica xG paired.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Feature</th>
                  <th className="py-1 pr-2">coverage_paired</th>
                  <th className="py-1 pr-2">coverage_global</th>
                  <th className="py-1 pr-2">Spearman TG</th>
                  <th className="py-1 pr-2">AUC ≥2</th>
                  <th className="py-1 pr-2">AUC ≥3</th>
                  <th className="py-1 pr-2">AUC BTTS</th>
                </tr>
              </thead>
              <tbody>
                {xgSignals.map((feature) => (
                  <tr key={String(feature.feature_key)} className="border-t border-slate-100">
                    <td className="py-1.5 pr-2 font-medium text-slate-800">{String(feature.feature_key ?? '—')}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{String(feature.coverage_paired ?? '—')}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{String(feature.coverage_global ?? '—')}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{String(feature.total_goals_ft_spearman ?? '—')}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{String(feature.goals_ge_2_auc ?? '—')}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{String(feature.goals_ge_3_auc ?? '—')}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{String(feature.btts_ft_auc ?? '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Raccomandazioni per pilastro">
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(pillarRecommendations).map(([pillar, data]) => {
            const primary = Array.isArray(data.candidate_core) ? data.candidate_core : []
            const secondary = Array.isArray(data.candidate_secondary) ? data.candidate_secondary : []
            const excluded = Array.isArray(data.excluded) ? data.excluded : []
            return (
              <div key={pillar} className="rounded-lg border border-slate-100 bg-slate-50/80 p-3">
                <h3 className="text-xs font-semibold text-slate-900">{PILLAR_LABELS[pillar] ?? pillar}</h3>
                <Kv label="Candidate core" value={primary.join(', ') || '—'} />
                <Kv label="Candidate secondarie" value={secondary.join(', ') || '—'} />
                <Kv label="Escluse / insufficient" value={excluded.join(', ') || '—'} />
              </div>
            )
          })}
        </div>
      </Section>

      <Section title="Dipendenze e ridondanza">
        <Kv label="VIF status" value={(redundancy.vif as Record<string, unknown> | undefined)?.status} />
        <Kv label="Cluster |ρ|≥0.80" value={(redundancy.cluster_counts as Record<string, unknown> | undefined)?.['0.8']} />
        <p className="mb-1 mt-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">Duplicati esatti</p>
        {exactDuplicates.length ? exactDuplicates.map(([key, d]) => (
          <Kv key={key} label={key} value={`== ${Array.isArray(d.source_features) ? d.source_features.join(', ') : '—'}`} />
        )) : <p className="text-xs text-slate-500">Nessuno.</p>}
        <p className="mb-1 mt-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">Feature derivate</p>
        {derived.length ? derived.map(([key, d]) => (
          <Kv key={key} label={key} value={`da ${Array.isArray(d.source_features) ? d.source_features.join(' + ') : '—'}`} />
        )) : <p className="text-xs text-slate-500">Nessuna.</p>}
        <p className="mb-1 mt-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">Rappresentanti cluster</p>
        {representatives.length ? representatives.map(([key, m]) => (
          <Kv key={key} label={String(m.redundancy_cluster_id ?? key)} value={key} />
        )) : <p className="text-xs text-slate-500">Nessun cluster ρ≥0.80.</p>}
      </Section>

      <Section title="Decisione finestre rolling">
        <div className="space-y-2">
          {Array.isArray(rolling.groups) ? rolling.groups.map((group) => {
            const g = group as Record<string, unknown>
            return (
              <div key={String(g.group)} className="rounded-lg border border-slate-100 bg-slate-50/80 p-3 text-xs">
                <Kv label="Gruppo" value={g.group} />
                <Kv label="Raccomandazione" value={g.recommendation} />
                <Kv label="Selezionata" value={g.selected_feature} />
                <Kv label="Secondaria" value={g.secondary_feature} />
                <Kv label="Escluse" value={Array.isArray(g.excluded_redundant_features) ? g.excluded_redundant_features.join(', ') : '—'} />
                <Kv label="Evidenza" value={g.evidence_level} />
                {g.motivation ? <p className="mt-1 text-slate-600">{String(g.motivation)}</p> : null}
              </div>
            )
          }) : <JsonBlock data={rolling} />}
        </div>
      </Section>

      <Section title="Decisione metrica di stabilità">
        <Kv label="Preferred" value={stability.preferred_stability_metric} />
        <Kv label="Secondary" value={stability.secondary_stability_metric} />
        <Kv label="Excluded" value={Array.isArray(stability.excluded_or_unstable_metrics) ? stability.excluded_or_unstable_metrics.join(', ') : '—'} />
        <Kv label="Raccomandazione" value={stability.recommendation} />
        <Kv label="Evidenza" value={stability.evidence_level} />
        {stability.motivation ? <p className="mt-2 text-xs text-slate-600">{String(stability.motivation)}</p> : null}
      </Section>

      <Section title="Stabilità temporale">
        <JsonBlock data={temporal.block_sizes} />
      </Section>

      <Section title="Valore xG e bias di disponibilità">
        <Kv label="Stato" value={xg.status} />
        <Kv label="Coppie xG" value={xg.paired_n} />
        <Kv label="Valutazione xG" value={xg.xg_value_assessment ?? xg.assessment} />
        <Kv label="Livello evidenza" value={xg.evidence_level} />
        <Kv label="Fold temporali" value={(xg.temporal_cv as Record<string, unknown> | undefined)?.fold_count} />
        <p className="mb-1 mt-3 text-[11px] font-medium uppercase tracking-wide text-slate-400">Bias di disponibilità</p>
        <JsonBlock data={statistics.xg_availability_bias_report} />
        <p className="mb-1 mt-3 text-[11px] font-medium uppercase tracking-wide text-slate-400">Metriche modello</p>
        <JsonBlock data={xg.models} />
      </Section>

      <Section title="Raccomandazioni feature">
        {!recommendations.length ? (
          <p className="text-xs text-slate-500">Nessuna raccomandazione disponibile.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Feature</th>
                  <th className="py-1 pr-2">Pilastro</th>
                  <th className="py-1 pr-2">Dep</th>
                  <th className="py-1 pr-2">Ridondanza</th>
                  <th className="py-1 pr-2">Esito</th>
                </tr>
              </thead>
              <tbody>
                {recommendations.map((feature) => (
                  <tr key={String(feature.feature_key)} className="border-t border-slate-100">
                    <td className="py-1.5 pr-2 font-medium text-slate-800">{String(feature.feature_key ?? '—')}</td>
                    <td className="py-1.5 pr-2">{PILLAR_LABELS[String(feature.pillar)] ?? String(feature.pillar ?? '—')}</td>
                    <td className="py-1.5 pr-2">{String(feature.dependency_type ?? '—')}</td>
                    <td className="py-1.5 pr-2">{String(feature.redundancy_summary ?? '—')}</td>
                    <td className="py-1.5 pr-2"><RecommendationBadge recommendation={feature.recommendation} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Readiness Fase 1D">
        <div className={`rounded-lg border px-3 py-2 text-sm ${readyFor1d ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : 'border-amber-200 bg-amber-50 text-amber-950'}`}>
          {readyFor1d ? 'Pronto per Fase 1D (candidate indices)' : 'Analisi Fase 1C incompleta — non pronto per Fase 1D'}
        </div>
        <Kv label="Passo consigliato" value={readiness.recommended_next_step} />
        {readinessFlags.map((key) => (
          <Kv key={key} label={key} value={readiness[key] === true ? 'true' : 'false'} />
        ))}
        <Kv label="Blocking issues" value={Array.isArray(readiness.blocking_issues) ? readiness.blocking_issues.join(', ') || '—' : '—'} />
        <Kv
          label="Blocking details"
          value={Array.isArray(readiness.blocking_details) ? readiness.blocking_details.join(', ') || '—' : '—'}
        />
        <Kv label="Versione statistics" value={statistics.version} />
      </Section>

      <Section title="Performance per fase">
        {Object.entries(performance).map(([label, value]) => (
          <Kv key={label} label={label} value={value} />
        ))}
      </Section>
    </div>
  )
}

function IndicesBody({
  indices,
  onExport,
  exportBusy,
  exportError,
}: {
  indices: GoalIntensityV5CandidateIndicesResponse
  onExport: (kind: GoalIntensityCandidateIndicesExportKind) => void
  exportBusy: boolean
  exportError: string | null
}) {
  const limitations = indices.research_limitations ?? {}
  const cohort = indices.cohort_summary ?? {}
  const normalization = indices.normalization_summary ?? {}
  const definitions = indices.candidate_definitions ?? {}
  const composites = indices.composite_metrics ?? {}
  const pillars = indices.pillar_metrics ?? {}
  const temporal = indices.temporal_metrics ?? {}
  const ablation = indices.ablation_summary ?? {}
  const redundancy = indices.pillar_redundancy ?? {}
  const paired = indices.paired_candidate_comparisons ?? {}
  const tempoBaseline = indices.tempo_baseline_comparison ?? {}
  const pareto = indices.pareto_analysis ?? {}
  const xg = indices.xg_optional_analysis ?? {}
  const protocol = indices.prospective_validation_protocol ?? {}
  const readiness = indices.phase_2a_readiness ?? {}
  const performance = indices.performance ?? {}
  const expanding = (temporal.expanding as Record<string, unknown> | undefined) ?? {}
  const giA = (composites.GI_A_STRICT_CORE as Record<string, unknown> | undefined) ?? {}
  const giAGe2 = (giA.goals_ge_2 as Record<string, unknown> | undefined) ?? {}
  const giATg = (giA.total_goals_ft as Record<string, unknown> | undefined) ?? {}
  const exportKinds: GoalIntensityCandidateIndicesExportKind[] = [
    'summary',
    'candidate_definitions',
    'candidate_scores',
    'pillar_metrics',
    'composite_metrics',
    'temporal_metrics',
    'decile_calibration',
    'ablation_analysis',
    'paired_candidate_comparison',
    'pillar_redundancy',
    'xg_optional_enrichment',
    'prospective_validation_protocol',
    'calibrated_predictions',
    'temporal_fold_metrics',
  ]
  const gateKeys = [
    'binary_calibration_verified',
    'paired_comparison_dimensionally_valid',
    'paired_delta_direction_verified',
    'ablation_calibrated',
    'expanding_validation_all_candidates',
    'expanding_validation_all_targets',
    'tempo_baseline_comparison_complete',
    'prospective_start_strictly_after_freeze',
    'temporal_validation_complete',
  ]

  return (
    <div className="space-y-4">
      <Section title="Limitazioni research">
        <div className="grid gap-2 sm:grid-cols-2">
          <Kv label="Eligibility engine" value={String(limitations.eligibility_engine_version ?? '—')} />
          <Kv label="Validation status" value={String(limitations.validation_status ?? '—')} />
        </div>
        <p className="mt-2 text-xs text-slate-600">{String(limitations.note ?? '')}</p>
      </Section>

      <Section title="Coorte">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Kv label="Core min10" value={String(cohort.core_min10 ?? '—')} />
          <Kv label="Core min20" value={String(cohort.core_min20 ?? '—')} />
          <Kv label="Analizzate" value={String(cohort.primary_analyzed ?? '—')} />
          <Kv label="xG paired" value={String(cohort.xg_complete_paired ?? '—')} />
        </div>
      </Section>

      <Section title="Normalizzazione ECDF (train-only)">
        <Kv label="Metodo" value={String(normalization.method ?? '—')} />
        <Kv label="Fit split" value={String(normalization.fit_split ?? '—')} />
        <p className="mt-2 text-xs text-slate-600">
          Hard excluded: {Array.isArray(normalization.hard_excluded_features)
            ? (normalization.hard_excluded_features as string[]).join(', ')
            : '—'}
        </p>
      </Section>

      <Section title="Calibrazione (non score/100)">
        <p className="text-xs text-slate-600">
          Brier e log loss usano probabilità da regressione logistica train-only. MAE/RMSE da
          regressione lineare train-only su total_goals. GI_A è baseline trasparente, non
          automaticamente «superiore».
        </p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <Kv label="TG method" value={String(giATg.calibration_method ?? '—')} />
          <Kv label="TG MAE" value={String(giATg.mae ?? '—')} />
          <Kv label="TG RMSE" value={String(giATg.rmse ?? '—')} />
          <Kv label="Binary method" value={String(giAGe2.calibration_method ?? '—')} />
          <Kv label="ge2 Brier (cal)" value={String(giAGe2.brier ?? '—')} />
          <Kv label="ge2 AUC" value={String(giAGe2.auc ?? '—')} />
        </div>
      </Section>

      <Section title="Primary / Challenger / Pareto">
        <div className="grid gap-2 sm:grid-cols-2">
          <Kv label="Primary (baseline)" value={String(indices.primary_candidate ?? '—')} />
          <Kv label="Challenger" value={String(indices.challenger_candidate ?? '—')} />
          <Kv label="Evidence" value={String(pareto.selection_evidence_level ?? '—')} />
          <Kv
            label="Nominal front"
            value={
              Array.isArray(pareto.nominal_pareto_front)
                ? (pareto.nominal_pareto_front as string[]).join(', ')
                : Array.isArray(pareto.pareto_front_candidates)
                  ? (pareto.pareto_front_candidates as string[]).join(', ')
                  : '—'
            }
          />
          <Kv
            label="Supported front"
            value={
              Array.isArray(pareto.statistically_supported_pareto_front)
                ? (pareto.statistically_supported_pareto_front as string[]).join(', ')
                : '—'
            }
          />
          <Kv
            label="MT1 competitive"
            value={String(pareto.tempo_only_baseline_competitive ?? tempoBaseline.tempo_only_baseline_competitive ?? '—')}
          />
        </div>
        <p className="mt-2 text-xs text-slate-600">{String(pareto.selection_motivation ?? '')}</p>
      </Section>

      <Section title="MT1 vs compositi">
        <div className="grid gap-2 sm:grid-cols-2">
          <Kv label="composite_value_over_tempo" value={String(tempoBaseline.composite_value_over_tempo ?? '—')} />
          <Kv label="tempo_only_baseline_competitive" value={String(tempoBaseline.tempo_only_baseline_competitive ?? '—')} />
          <Kv label="GI_A vs MT1" value={String(tempoBaseline.GI_A_vs_MT1 ?? '—')} />
          <Kv label="GI_B vs MT1" value={String(tempoBaseline.GI_B_vs_MT1 ?? '—')} />
        </div>
        <p className="mt-2 text-xs text-slate-600">{String(tempoBaseline.note ?? '')}</p>
      </Section>

      <Section title="Paired delta (calibrati)">
        <p className="text-xs text-slate-600">
          delta MAE/RMSE/Brier &lt; 0 favorisce left; delta Spearman/AUC &gt; 0 favorisce left. Mai
          score 0–100 vs gol.
        </p>
        <JsonBlock data={paired} />
      </Section>

      <Section title="Ablation calibrata">
        <JsonBlock data={ablation} />
      </Section>

      <Section title="Expanding temporal (tutti i candidati)">
        <div className="grid gap-2 sm:grid-cols-2">
          <Kv label="Status" value={String(expanding.status ?? '—')} />
          <Kv label="Fold count" value={String(expanding.fold_count ?? '—')} />
          <Kv label="All candidates" value={String(expanding.all_candidates_present ?? '—')} />
          <Kv label="All targets" value={String(expanding.all_targets_present ?? '—')} />
        </div>
        <JsonBlock data={expanding.candidates} />
      </Section>

      <Section title="Metriche compositi">
        <JsonBlock data={composites} />
      </Section>

      <Section title="Metriche pilastri">
        <JsonBlock data={pillars} />
      </Section>

      <Section title="Ridondanza pilastri">
        <JsonBlock data={redundancy} />
      </Section>

      <Section title="xG optional (paired)">
        <div className="grid gap-2 sm:grid-cols-2">
          <Kv label="Status" value={String(xg.xg_status ?? '—')} />
          <Kv label="Assessment" value={String(xg.xg_value_assessment ?? '—')} />
          <Kv label="Paired n" value={String(xg.paired_n ?? '—')} />
          <Kv label="Promoted to core" value={String(xg.promoted_to_core ?? false)} />
        </div>
      </Section>

      <Section title="Protocollo prospettico">
        <div className="grid gap-2 sm:grid-cols-2">
          <Kv label="Freeze UTC" value={String(protocol.candidate_definition_frozen_at ?? '—')} />
          <Kv label="First prospective scan" value={String(protocol.first_prospective_scan_date ?? '—')} />
          <Kv label="Window start" value={String(protocol.prospective_window_started_at ?? '—')} />
          <Kv label="Status" value={String(protocol.protocol_status ?? '—')} />
          <Kv label="Collected" value={String(protocol.prospective_matches_collected ?? '—')} />
          <Kv label="Minimum" value={String(protocol.minimum_prospective_matches ?? '—')} />
        </div>
        <p className="mt-2 text-xs text-slate-600">{String(protocol.note ?? '')}</p>
      </Section>

      <Section title="Readiness Fase 2A">
        <Kv label="Ready" value={String(readiness.ready_for_phase_2a ?? false)} />
        <Kv label="Next step" value={String(readiness.recommended_next_step ?? '—')} />
        <ul className="mt-2 space-y-1 text-xs text-slate-700">
          {gateKeys.map((key) => (
            <li key={key}>
              {key}: {String(readiness[key] ?? '—')}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-slate-600">
          Blocking:{' '}
          {Array.isArray(readiness.blocking_issues)
            ? (readiness.blocking_issues as string[]).join(', ') || 'nessuno'
            : '—'}
        </p>
      </Section>

      <Section title="Performance">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <Kv label="Elapsed ms" value={String(performance.elapsed_ms ?? '—')} />
          <Kv label="Payload bytes" value={String(performance.response_payload_bytes ?? '—')} />
          <Kv label="v4 unchanged" value={String(performance.v4_unchanged ?? '—')} />
        </div>
      </Section>

      <Section title="Export">
        <div className="flex flex-wrap gap-2">
          {exportKinds.map((kind) => (
            <button
              key={kind}
              type="button"
              disabled={exportBusy}
              onClick={() => onExport(kind)}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {kind}
            </button>
          ))}
        </div>
        {exportError ? (
          <p className="mt-2 text-xs text-red-700">{exportError}</p>
        ) : null}
      </Section>

      <Section title="Preview score grezzi (≤100)">
        <JsonBlock data={indices.preview_rows} />
      </Section>

      <Section title="Semantica pilastri">
        <p className="text-xs text-slate-600">
          Alto = più intensità potenziale. Solidità display = 100 − DV; stabilità display = 100 − OV.
          I display non entrano nei compositi.
        </p>
        <JsonBlock data={definitions} />
      </Section>
    </div>
  )
}

export function RicercaIntensitaGoalPage() {
  const [tab, setTab] = useState<LabTab>('audit')
  const [dateFrom, setDateFrom] = useState(() => isoDaysAgoLocal(90))
  const [dateTo, setDateTo] = useState(() => todayLocalIso())
  const [competitionId, setCompetitionId] = useState('')
  const [availability, setAvailability] = useState<GoalIntensityV5AvailabilityResponse | null>(null)
  const [availabilityError, setAvailabilityError] = useState<string | null>(null)
  const filters = { dateFrom, dateTo, competitionId }
  const { loading, error, audit, runAudit } = useCecchinoGoalIntensityV5Audit(filters)
  const {
    loading: datasetLoading,
    error: datasetError,
    dataset,
    runDataset,
  } = useCecchinoGoalIntensityV5Dataset(filters)
  const {
    loading: statisticsLoading,
    error: statisticsError,
    statistics,
    runStatistics,
  } = useCecchinoGoalIntensityV5Statistics(filters)
  const {
    loading: indicesLoading,
    error: indicesError,
    indices,
    runCandidateIndices,
  } = useCecchinoGoalIntensityV5CandidateIndices(filters)
  const [exportBusy, setExportBusy] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const handleDatasetExport = async (kind: GoalIntensityDatasetExportKind) => {
    setExportBusy(true)
    setExportError(null)
    try {
      const compId = competitionId.trim() ? Number(competitionId) : null
      const { blob, filename } = await postGoalIntensityV5DatasetExport(kind, {
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: compId != null && Number.isFinite(compId) && compId > 0 ? compId : null,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setExportError(classifyGoalIntensityFetchError(err, 'export'))
    } finally {
      setExportBusy(false)
    }
  }

  const handleStatisticsExport = async (kind: GoalIntensityStatisticsExportKind) => {
    setExportBusy(true)
    setExportError(null)
    try {
      const compId = competitionId.trim() ? Number(competitionId) : null
      const { blob, filename } = await postGoalIntensityV5StatisticsExport(kind, {
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: compId != null && Number.isFinite(compId) && compId > 0 ? compId : null,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setExportError(formatFetchError(err))
    } finally {
      setExportBusy(false)
    }
  }

  const handleIndicesExport = async (kind: GoalIntensityCandidateIndicesExportKind) => {
    setExportBusy(true)
    setExportError(null)
    try {
      const compId = competitionId.trim() ? Number(competitionId) : null
      const { blob, filename } = await postGoalIntensityV5CandidateIndicesExport(kind, {
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: compId != null && Number.isFinite(compId) && compId > 0 ? compId : null,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setExportError(formatFetchError(err))
    } finally {
      setExportBusy(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const avail = await fetchGoalIntensityV5Availability()
        if (cancelled) return
        setAvailability(avail)
        setAvailabilityError(null)
        if (avail.earliest_kickoff_date && avail.latest_kickoff_date) {
          setDateFrom(avail.earliest_kickoff_date)
          setDateTo(avail.latest_kickoff_date)
        }
      } catch (err) {
        if (cancelled) return
        setAvailabilityError(formatFetchError(err))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const inputClass =
    'mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm shadow-sm focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-100'

  const rangeLabel =
    availability?.earliest_kickoff_date && availability?.latest_kickoff_date
      ? `Scansioni Cecchino Today eleggibili dal ${availability.earliest_kickoff_date} al ${availability.latest_kickoff_date} (minimo assoluto 19/06/2026)`
      : 'La ricerca Intensità Goal utilizza le scansioni Cecchino Today disponibili dal 19/06/2026.'

  const busy =
    tab === 'audit'
      ? loading
      : tab === 'dataset'
        ? datasetLoading
        : tab === 'statistics'
          ? statisticsLoading
          : indicesLoading

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6 bg-gradient-to-b from-slate-50/80 to-white pb-10"
    >
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
          Ricerca Intensità Goal v5
        </h1>
        <p
          role="status"
          className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950"
        >
          Lab research: nessuna formula produttiva viene modificata.
        </p>
        {rangeLabel ? (
          <p role="status" className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800">
            {rangeLabel}
            {availability?.finished_fixtures_with_result != null
              ? ` (${availability.finished_fixtures_with_result} fixture FT).`
              : '.'}
          </p>
        ) : null}
        {availabilityError ? (
          <CecchinoStatusMessage
            variant="error"
            title="Disponibilità dati"
            message={availabilityError}
          />
        ) : null}
      </header>

      <div className="flex flex-wrap gap-1 border-b border-slate-200 pb-1">
        <button
          type="button"
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
            tab === 'audit' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
          }`}
          onClick={() => setTab('audit')}
        >
          Audit copertura
        </button>
        <button
          type="button"
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
            tab === 'dataset' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
          }`}
          onClick={() => setTab('dataset')}
        >
          Dataset Fase 1B
        </button>
        <button
          type="button"
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
            tab === 'statistics' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
          }`}
          onClick={() => setTab('statistics')}
        >
          Analisi Fase 1C
        </button>
        <button
          type="button"
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
            tab === 'indices' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
          }`}
          onClick={() => setTab('indices')}
        >
          Indici Fase 1D
        </button>
      </div>

      <section className="sticky top-0 z-20 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm backdrop-blur-sm">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="text-xs font-medium text-slate-600">
            Scan date da
            <input
              type="date"
              className={inputClass}
              value={dateFrom}
              min="2026-06-19"
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Scan date a
            <input
              type="date"
              className={inputClass}
              value={dateTo}
              min="2026-06-19"
              onChange={(e) => setDateTo(e.target.value)}
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Competition ID
            <input
              type="number"
              min={1}
              className={inputClass}
              value={competitionId}
              onChange={(e) => setCompetitionId(e.target.value)}
              placeholder="opzionale"
            />
          </label>
        </div>
        <div className="mt-4">
          {tab === 'audit' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void runAudit()}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
            >
              {busy ? (
                <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : null}
              Esegui audit
            </button>
          ) : tab === 'dataset' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void runDataset()}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
            >
              {busy ? (
                <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : null}
              Costruisci dataset
            </button>
          ) : tab === 'statistics' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void runStatistics()}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
            >
              {busy ? (
                <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : null}
              Esegui analisi Fase 1C
            </button>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => void runCandidateIndices()}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
            >
              {busy ? (
                <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : null}
              Esegui indici Fase 1D
            </button>
          )}
        </div>
      </section>

      {busy ? (
        <div className="space-y-3" aria-busy="true">
          <div className="h-24 animate-pulse rounded-xl bg-slate-100" />
          <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
          <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
        </div>
      ) : null}

      {tab === 'audit' ? (
        <>
          {error ? <CecchinoStatusMessage variant="error" title="Errore audit" message={error} /> : null}
          {!loading && !error && !audit ? (
            <p className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
              Imposta il periodo e premi «Esegui audit» per avviare l’analisi storica.
            </p>
          ) : null}
          {!loading && audit ? <AuditBody audit={audit} /> : null}
        </>
      ) : tab === 'dataset' ? (
        <>
          {datasetError ? (
            <CecchinoStatusMessage variant="error" title="Errore dataset" message={datasetError} />
          ) : null}
          {!datasetLoading && !datasetError && !dataset ? (
            <p className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
              Imposta il periodo e premi «Costruisci dataset» per la Fase 1B.
            </p>
          ) : null}
          {!datasetLoading && dataset ? (
            <DatasetBody
              dataset={dataset}
              onExport={(kind) => void handleDatasetExport(kind)}
              exportBusy={exportBusy}
              exportError={exportError}
            />
          ) : null}
        </>
      ) : tab === 'statistics' ? (
        <>
          {statisticsError ? (
            <CecchinoStatusMessage
              variant="error"
              title="Errore analisi Fase 1C"
              message={statisticsError}
            />
          ) : null}
          {!statisticsLoading && !statisticsError && !statistics ? (
            <p className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
              Imposta il periodo e premi «Esegui analisi Fase 1C» per avviare l’analisi statistica.
            </p>
          ) : null}
          {!statisticsLoading && statistics ? (
            <StatisticsBody
              statistics={statistics}
              onExport={(kind) => void handleStatisticsExport(kind)}
              exportBusy={exportBusy}
              exportError={exportError}
            />
          ) : null}
        </>
      ) : (
        <>
          {indicesError ? (
            <CecchinoStatusMessage
              variant="error"
              title="Errore indici Fase 1D"
              message={indicesError}
            />
          ) : null}
          {!indicesLoading && !indicesError && !indices ? (
            <p className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
              Imposta il periodo e premi «Esegui indici Fase 1D» per costruire i candidati 0–100.
            </p>
          ) : null}
          {!indicesLoading && indices ? (
            <IndicesBody
              indices={indices}
              onExport={(kind) => void handleIndicesExport(kind)}
              exportBusy={exportBusy}
              exportError={exportError}
            />
          ) : null}
        </>
      )}
    </motion.div>
  )
}
