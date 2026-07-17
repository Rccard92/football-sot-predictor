import { useEffect, useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { CecchinoStatusMessage } from '../components/cecchino/CecchinoStatusMessage'
import { useCecchinoGoalIntensityV5Audit } from '../hooks/useCecchinoGoalIntensityV5Audit'
import {
  buildGoalIntensityAuditJsonFilename,
  buildGoalIntensityFeatureInventoryCsvFilename,
  buildGoalIntensityFixtureAuditCsvFilename,
  featureInventoryToCsv,
  fetchGoalIntensityV5Availability,
  fixtureAuditToCsv,
  isGoalIntensityAuditDegraded,
  isGoalIntensityAuditUnusable,
  type GoalIntensityFixtureAuditRow,
  type GoalIntensityV5AuditResponse,
  type GoalIntensityV5AvailabilityResponse,
} from '../lib/cecchinoGoalIntensityV5ResearchApi'
import { downloadJsonFile, downloadTextFile } from '../lib/downloadJsonFile'
import { isoDaysAgoLocal, todayLocalIso } from '../utils/dateLocal'
import { formatFetchError } from '../utils/formatFetchError'

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

export function RicercaIntensitaGoalPage() {
  const [dateFrom, setDateFrom] = useState(() => isoDaysAgoLocal(90))
  const [dateTo, setDateTo] = useState(() => todayLocalIso())
  const [competitionId, setCompetitionId] = useState('')
  const [availability, setAvailability] = useState<GoalIntensityV5AvailabilityResponse | null>(null)
  const [availabilityError, setAvailabilityError] = useState<string | null>(null)
  const { loading, error, audit, runAudit } = useCecchinoGoalIntensityV5Audit({
    dateFrom,
    dateTo,
    competitionId,
  })

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
      ? `Dati locali disponibili dal ${availability.earliest_kickoff_date} al ${availability.latest_kickoff_date}`
      : null

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
          Audit preliminare: nessuna formula produttiva viene modificata.
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

      <section className="sticky top-0 z-20 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm backdrop-blur-sm">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="text-xs font-medium text-slate-600">
            Data da
            <input
              type="date"
              className={inputClass}
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Data a
            <input
              type="date"
              className={inputClass}
              value={dateTo}
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
          <button
            type="button"
            disabled={loading}
            onClick={() => void runAudit()}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
          >
            {loading ? (
              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : null}
            Esegui audit
          </button>
        </div>
      </section>

      {loading ? (
        <div className="space-y-3" aria-busy="true">
          <div className="h-24 animate-pulse rounded-xl bg-slate-100" />
          <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
          <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
        </div>
      ) : null}

      {error ? <CecchinoStatusMessage variant="error" title="Errore audit" message={error} /> : null}

      {!loading && !error && !audit ? (
        <p className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
          Imposta il periodo e premi «Esegui audit» per avviare l’analisi storica.
        </p>
      ) : null}

      {!loading && audit ? <AuditBody audit={audit} /> : null}
    </motion.div>
  )
}
