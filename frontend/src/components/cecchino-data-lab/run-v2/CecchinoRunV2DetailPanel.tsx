import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  RUN_V2_EXPORT_FILES,
  downloadRunV2Export,
  formatRunV2Date,
  getRunV2ExportManifest,
  isRunV2Completed,
  runV2ScopeLabel,
  runV2StatusLabel,
  type CecchinoRunV2,
  type CecchinoRunV2ExportManifest,
  type RunV2ExportFile,
} from '../../../lib/cecchinoRunV2Api'
import { AdminHttpError } from '../../../lib/api'
import { AdminLoginDialog } from './AdminLoginDialog'
import { RunV2Stat } from './RunV2Stat'

type Props = {
  run: CecchinoRunV2
  onClose: () => void
}

export function CecchinoRunV2DetailPanel({ run, onClose }: Props) {
  const [manifest, setManifest] = useState<CecchinoRunV2ExportManifest | null>(null)
  const [manifestBusy, setManifestBusy] = useState(false)
  const [downloading, setDownloading] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<(() => Promise<void>) | null>(null)

  const completed = isRunV2Completed(run)
  const summary = run.summary
  const competitions = summary?.competitions ?? []
  const marketCoverage = summary?.market_coverage ?? []
  const statsCoverage = summary?.extra_stats_coverage
  const leakage = run.leakage_audit ?? summary?.leakage_audit ?? null
  const warnings = Array.isArray(run.warnings) ? run.warnings : []

  const seasons = Array.from(new Set(competitions.map((c) => c.season_label))).sort()

  useEffect(() => {
    setManifest(null)
  }, [run.run_id])

  const handledAsAuthPrompt = (e: unknown, retry: () => Promise<void>): boolean => {
    if (!(e instanceof AdminHttpError) || e.status !== 401) return false
    setPendingAction(() => retry)
    return true
  }

  const loadManifest = useCallback(async () => {
    setManifestBusy(true)
    try {
      setManifest(await getRunV2ExportManifest(run.run_id))
    } catch (e) {
      if (handledAsAuthPrompt(e, () => loadManifest())) return
      toast.error(e instanceof Error ? e.message : 'Manifest export non disponibile')
    } finally {
      setManifestBusy(false)
    }
  }, [run.run_id])

  const onDownload = async (file: RunV2ExportFile) => {
    setDownloading(file)
    try {
      await downloadRunV2Export(run.run_id, file)
      toast.success(`Download avviato: ${file}`)
    } catch (e) {
      if (handledAsAuthPrompt(e, () => onDownload(file))) return
      toast.error(e instanceof Error ? e.message : 'Download fallito')
    } finally {
      setDownloading(null)
    }
  }

  return (
    <section className="lab-card rounded-xl p-4" data-testid={`run-v2-detail-${run.run_id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-semibold">
            RUN V2 #{run.run_id} — {runV2StatusLabel(run.effective_status)}{' '}
            <span className="text-sm font-normal" style={{ color: 'var(--lab-muted)' }}>
              ({runV2ScopeLabel(run)})
            </span>
          </h4>
          <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            {run.run_version}
            {run.season_label ? ` · ${run.season_label}` : ''} · creata il{' '}
            {formatRunV2Date(run.created_at)}
          </p>
        </div>
        <button
          type="button"
          className="lab-btn rounded-md px-3 py-1.5 text-sm"
          onClick={onClose}
        >
          Chiudi
        </button>
      </div>

      <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <RunV2Stat
          label="Match processati"
          value={`${run.matches_processed}/${run.matches_total}`}
        />
        <RunV2Stat label="Match in errore" value={String(run.matches_error)} />
        <RunV2Stat label="Righe mercato" value={String(run.market_rows_written)} />
        <RunV2Stat
          label="Leakage violations"
          value={String(run.leakage_violations)}
          tone={run.leakage_violations > 0 ? 'danger' : 'ok'}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <h5 className="text-sm font-semibold">Competizioni e stagioni</h5>
          {competitions.length ? (
            <>
              <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
                {competitions.length} competizioni · stagioni: {seasons.join(', ') || '—'}
              </p>
              <div className="mt-2 max-h-52 overflow-auto">
                <table className="lab-table w-full text-xs">
                  <thead>
                    <tr>
                      <th>Competizione</th>
                      <th>Stagione</th>
                      <th>Match</th>
                      <th>Eleggibili</th>
                    </tr>
                  </thead>
                  <tbody>
                    {competitions.map((c) => (
                      <tr key={`${c.competition}-${c.season_label}`}>
                        <td>{c.competition}</td>
                        <td>{c.season_label}</td>
                        <td>{c.matches}</td>
                        <td>
                          {c.eligible_vs_target ??
                            (c.eligible_core != null ? String(c.eligible_core) : '—')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
              Disponibili al termine della run.
            </p>
          )}
        </div>

        <div>
          <h5 className="text-sm font-semibold">Copertura quote</h5>
          {marketCoverage.length ? (
            <div className="mt-2 max-h-52 overflow-auto">
              <table className="lab-table w-full text-xs">
                <thead>
                  <tr>
                    <th>Mercato</th>
                    <th>Layer</th>
                    <th>Righe</th>
                    <th>Con quota</th>
                    <th>%</th>
                  </tr>
                </thead>
                <tbody>
                  {marketCoverage.map((m) => (
                    <tr key={`${m.market_key}-${m.observation_layer}`}>
                      <td>{m.export_key}</td>
                      <td>{m.observation_layer === 'core_strict' ? 'STRICT' : 'ECONOMIC'}</td>
                      <td>{m.rows}</td>
                      <td>{m.rows_with_quote}</td>
                      <td>{m.quote_coverage_pct ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
              Disponibile al termine della run.
            </p>
          )}
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <h5 className="text-sm font-semibold">Copertura statistiche</h5>
          {statsCoverage ? (
            <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
              <RunV2Stat label="Snapshot" value={String(statsCoverage.snapshots ?? 0)} />
              <RunV2Stat
                label="Con storico precedente"
                value={String(statsCoverage.with_prior_history ?? 0)}
              />
              <RunV2Stat label="Con arbitro" value={String(statsCoverage.with_referee ?? 0)} />
              <RunV2Stat
                label="Copertura arbitro %"
                value={String(statsCoverage.referee_coverage_pct ?? '—')}
              />
            </div>
          ) : (
            <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
              Disponibile al termine della run.
            </p>
          )}
        </div>

        <div>
          <h5 className="text-sm font-semibold">Audit anti-leakage</h5>
          {leakage ? (
            <pre
              className="mt-2 max-h-40 overflow-auto rounded-md p-3 text-xs"
              style={{ background: 'rgba(0,0,0,0.25)' }}
            >
              {JSON.stringify(leakage, null, 2)}
            </pre>
          ) : (
            <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
              Nessun audit registrato.
            </p>
          )}
        </div>
      </div>

      <div className="mt-4">
        <h5 className="text-sm font-semibold">Avvisi</h5>
        {warnings.length ? (
          <ul className="mt-1 list-disc pl-5 text-sm text-amber-200">
            {warnings.map((w, i) => (
              <li key={i}>{typeof w === 'string' ? w : JSON.stringify(w)}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Nessun avviso.
          </p>
        )}
        {run.error && (
          <pre
            className="mt-2 max-h-40 overflow-auto rounded-md p-3 text-xs text-red-300"
            style={{ background: 'rgba(0,0,0,0.25)' }}
          >
            {JSON.stringify(run.error, null, 2)}
          </pre>
        )}
      </div>

      <div className="mt-4">
        <div className="flex flex-wrap items-center gap-3">
          <h5 className="text-sm font-semibold">Export disponibili</h5>
          <button
            type="button"
            className="lab-btn rounded-md px-3 py-1.5 text-xs"
            onClick={() => void loadManifest()}
            disabled={manifestBusy || !completed}
          >
            {manifestBusy ? 'Verifica…' : 'Verifica artefatti'}
          </button>
        </div>
        <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
          Gli artefatti sono rigenerati dal DB a ogni richiesta: nessun file resta sul disco.
        </p>
        {!completed && (
          <p className="mt-1 text-xs text-amber-200">
            L&apos;export si attiva quando la RUN è completata.
          </p>
        )}
        <ul className="mt-2 space-y-1 text-sm">
          {RUN_V2_EXPORT_FILES.map((file) => (
            <li key={file} className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="lab-btn rounded-md px-3 py-1 text-xs"
                data-testid={`run-v2-export-${run.run_id}-${file}`}
                disabled={!completed || downloading !== null}
                onClick={() => void onDownload(file)}
              >
                {downloading === file ? 'Download…' : file}
              </button>
              {manifest?.counts && file === 'FULL.csv' && (
                <span className="text-xs" style={{ color: 'var(--lab-muted)' }}>
                  {manifest.counts.full_rows ?? '—'} righe ·{' '}
                  {manifest.counts.full_columns ?? '—'} colonne
                </span>
              )}
              {manifest?.counts && file === 'core_markets_long.csv' && (
                <span className="text-xs" style={{ color: 'var(--lab-muted)' }}>
                  {manifest.counts.core_markets_long_rows ?? '—'} righe
                </span>
              )}
              {manifest?.counts && file === 'SOURCE_RAW.csv' && (
                <span className="text-xs" style={{ color: 'var(--lab-muted)' }}>
                  {manifest.counts.source_raw_rows ?? '—'} righe ·{' '}
                  {manifest.counts.source_raw_columns ?? '—'} colonne
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      {pendingAction && (
        <AdminLoginDialog
          onClose={() => setPendingAction(null)}
          onSuccess={() => {
            const retry = pendingAction
            setPendingAction(null)
            void retry()
          }}
        />
      )}
    </section>
  )
}
