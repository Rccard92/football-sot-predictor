import { useEffect, useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { CecchinoStatusMessage } from '../components/cecchino/CecchinoStatusMessage'
import { useCecchinoGoalIntensityV5Audit } from '../hooks/useCecchinoGoalIntensityV5Audit'
import { useCecchinoGoalIntensityV5Dataset } from '../hooks/useCecchinoGoalIntensityV5Dataset'
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
  postGoalIntensityV5DatasetExport,
  type GoalIntensityDatasetExportKind,
  type GoalIntensityDatasetRow,
  type GoalIntensityFixtureAuditRow,
  type GoalIntensityV5AuditResponse,
  type GoalIntensityV5AvailabilityResponse,
  type GoalIntensityV5DatasetResponse,
} from '../lib/cecchinoGoalIntensityV5ResearchApi'
import { downloadJsonFile, downloadTextFile } from '../lib/downloadJsonFile'
import { isoDaysAgoLocal, todayLocalIso } from '../utils/dateLocal'
import { formatFetchError } from '../utils/formatFetchError'

type LabTab = 'audit' | 'dataset'

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

  const busy = tab === 'audit' ? loading : datasetLoading

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
          ) : (
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
      ) : (
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
      )}
    </motion.div>
  )
}
