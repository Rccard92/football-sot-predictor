import type {
  GoalIntensityV5PreviewExportKind,
  GoalIntensityV5PreviewListResponse,
  GoalIntensityV5PreviewMonitoringResponse,
  GoalIntensityV5PreviewRefreshResponse,
  GoalIntensityV5PreviewSnapshotRow,
} from '../../lib/cecchinoGoalIntensityV5PreviewApi'

type Props = {
  list: GoalIntensityV5PreviewListResponse | null
  monitoring: GoalIntensityV5PreviewMonitoringResponse | null
  lastRefresh: GoalIntensityV5PreviewRefreshResponse | null
  loading: boolean
  refreshing: boolean
  error: string | null
  statusFilter: string
  onStatusFilter: (v: string) => void
  onLoad: () => void
  onRefresh: () => void
  onExport: (kind: GoalIntensityV5PreviewExportKind) => void
  exportBusy: boolean
}

function pct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${Math.round(v * 100)}%`
}

function num(v: number | null | undefined, d = 1): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(d)
}

const EXPORTS: Array<[GoalIntensityV5PreviewExportKind, string]> = [
  ['summary', 'Summary JSON'],
  ['snapshots', 'Snapshots CSV'],
  ['completed-results', 'Completed CSV'],
  ['candidate-monitoring', 'Monitoring CSV'],
  ['calibration', 'Calibration JSON'],
  ['bundle-definition', 'Bundle JSON'],
]

export function GoalIntensityV5PreviewBody({
  list,
  monitoring,
  lastRefresh,
  loading,
  refreshing,
  error,
  statusFilter,
  onStatusFilter,
  onLoad,
  onRefresh,
  onExport,
  exportBusy,
}: Props) {
  const bundle = list?.bundle
  const items = list?.items ?? []
  const readiness = (monitoring?.phase_2b_readiness || {}) as Record<string, unknown>

  return (
    <div className="space-y-4">
      {error ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>
      ) : null}

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Preview Fase 2A</h2>
            <p className="mt-1 text-xs text-slate-500">
              Snapshot pre-match da bundle congelato. Nessun segnale betting. v4 invariata.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={loading}
              onClick={() => onLoad()}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Ricarica
            </button>
            <button
              type="button"
              disabled={refreshing || loading}
              onClick={() => onRefresh()}
              className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {refreshing ? 'Aggiornamento…' : 'Aggiorna Preview'}
            </button>
          </div>
        </div>

        {bundle ? (
          <>
            <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Bundle attivo" value={`#${bundle.bundle_id}`} />
              <Stat label="Versione" value={bundle.version} />
              <Stat label="Definition hash" value={bundle.candidate_definition_hash_short ?? '—'} />
              <Stat
                label="Raccolta prospettica avviata"
                value={(bundle.bundle_frozen_at ?? bundle.frozen_at)?.replace('T', ' ').slice(0, 19) ?? '—'}
              />
              <Stat
                label="Modalità"
                value={
                  bundle.prospective_start_mode === 'strict_after_actual_bundle_freeze'
                    ? 'Dopo il freeze effettivo'
                    : (bundle.prospective_start_mode ?? '—')
                }
              />
              <Stat
                label="Partite retrospettive congelate"
                value={String(bundle.retrospective_identity_count ?? 0)}
              />
              <Stat label="Snapshot dopo freeze" value={String(bundle.collected ?? 0)} />
              <Stat label="Concluse" value={String(bundle.completed ?? 0)} />
              <Stat label="Pending" value={String(bundle.pending ?? 0)} />
              <Stat label="Incomplete" value={String(bundle.incomplete ?? 0)} />
              <Stat label="Error" value={String(bundle.error ?? 0)} />
              <Stat
                label="Progresso verso 200"
                value={`${pct(bundle.progress_to_minimum)} (${bundle.completed ?? 0}/200)`}
              />
              <Stat label="Protocol status" value={bundle.protocol_status ?? '—'} />
              <Stat
                label="Primary / Challenger"
                value={`${bundle.primary_candidate ?? 'GI_A'} / ${bundle.challenger_candidate ?? 'GI_B'}`}
              />
            </dl>
            <p className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
              Le 200 partite rappresentano il campione minimo per la futura revisione della Fase 2B.
              La Preview è già operativa e raccoglie dati dalla prima scansione successiva al freeze.
            </p>
          </>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            Nessun bundle attivo. Esegui freeze (script o POST freeze) prima del refresh.
          </p>
        )}

        {lastRefresh?.counters ? (
          <p className="mt-3 text-xs text-slate-600">
            Ultimo refresh: created={lastRefresh.counters.created ?? 0}, updated=
            {lastRefresh.counters.updated ?? 0}, locked={lastRefresh.counters.locked ?? 0}, results=
            {lastRefresh.counters.results_attached ?? 0}
          </p>
        ) : null}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-slate-900">Monitoraggio prospettico</h3>
        <p className="mt-1 text-xs text-slate-500">
          Completate: {monitoring?.completed_prospective_matches ?? 0} /{' '}
          {monitoring?.minimum_prospective_matches ?? 200} — status: {monitoring?.status ?? '—'}
        </p>
        <p className="mt-2 text-xs text-slate-600">
          Phase 2B next: {String(readiness.recommended_next_step ?? 'continue_prospective_monitoring')}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs text-slate-600">
          Filtro stato
          <select
            className="ml-2 rounded border border-slate-300 px-2 py-1 text-sm"
            value={statusFilter}
            onChange={(e) => onStatusFilter(e.target.value)}
          >
            <option value="">tutti</option>
            <option value="pending">pending</option>
            <option value="locked">locked</option>
            <option value="completed">completed</option>
            <option value="incomplete">incomplete</option>
            <option value="error">error</option>
          </select>
        </label>
        <div className="flex flex-wrap gap-1">
          {EXPORTS.map(([kind, label]) => (
            <button
              key={kind}
              type="button"
              disabled={exportBusy || !bundle}
              onClick={() => onExport(kind)}
              className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
            <tr>
              {[
                'Data',
                'Kickoff',
                'Competizione',
                'Casa',
                'Trasferta',
                'Stato',
                'Snapshot',
                'Hist',
                'xG',
                'GI_A',
                'GI_B',
                'MT1',
                'GI_A−OV1',
                'Exp GI_A',
                'P≥2',
                'P≥3',
                'P BTTS',
                'Risultato',
                'Preview',
              ].map((h) => (
                <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={19} className="px-3 py-8 text-center text-slate-500">
                  {loading ? 'Caricamento…' : 'Nessuno snapshot. Premi «Aggiorna Preview».'}
                </td>
              </tr>
            ) : (
              items.map((row: GoalIntensityV5PreviewSnapshotRow) => (
                <tr key={row.id} className="border-b border-slate-100 text-slate-800">
                  <td className="whitespace-nowrap px-2 py-1.5">{row.scan_date ?? '—'}</td>
                  <td className="whitespace-nowrap px-2 py-1.5">
                    {row.kickoff?.slice(0, 16)?.replace('T', ' ') ?? '—'}
                  </td>
                  <td className="max-w-[8rem] truncate px-2 py-1.5">{row.competition_name ?? '—'}</td>
                  <td className="max-w-[8rem] truncate px-2 py-1.5">{row.home_team_name ?? '—'}</td>
                  <td className="max-w-[8rem] truncate px-2 py-1.5">{row.away_team_name ?? '—'}</td>
                  <td className="px-2 py-1.5">{row.snapshot_status ?? '—'}</td>
                  <td className="whitespace-nowrap px-2 py-1.5">
                    {row.source_snapshot_at?.slice(0, 16)?.replace('T', ' ') ?? '—'}
                  </td>
                  <td className="px-2 py-1.5">{row.history_sample_size ?? '—'}</td>
                  <td className="px-2 py-1.5">{row.xg_status ?? '—'}</td>
                  <td className="px-2 py-1.5">{num(row.GI_A)}</td>
                  <td className="px-2 py-1.5">{num(row.GI_B)}</td>
                  <td className="px-2 py-1.5">{num(row.MT1)}</td>
                  <td className="px-2 py-1.5">{num(row.GI_A_without_volatility)}</td>
                  <td className="px-2 py-1.5">{num(row.expected_goals_GI_A, 2)}</td>
                  <td className="px-2 py-1.5">{pct(row.p_ge2_GI_A)}</td>
                  <td className="px-2 py-1.5">{pct(row.p_ge3_GI_A)}</td>
                  <td className="px-2 py-1.5">{pct(row.p_btts_GI_A)}</td>
                  <td className="px-2 py-1.5">{row.total_goals_ft ?? '—'}</td>
                  <td className="px-2 py-1.5">{row.preview_status ?? '—'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 px-2.5 py-2">
      <dt className="text-[10px] uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 font-medium text-slate-900">{value}</dd>
    </div>
  )
}
