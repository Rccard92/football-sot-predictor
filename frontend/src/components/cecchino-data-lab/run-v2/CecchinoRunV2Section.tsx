import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import {
  RunV2ApiError,
  cancelRunV2,
  downloadRunV2Export,
  formatRunV2Date,
  getRunV2,
  isRunV2Active,
  isRunV2Completed,
  listRunsV2,
  preflightRunV2,
  resumeRunV2,
  runV2ScopeLabel,
  runV2StatusLabel,
  startRunV2,
  type CecchinoRunV2,
  type CecchinoRunV2Preflight,
} from '../../../lib/cecchinoRunV2Api'
import {
  DEFAULT_HISTORICAL_SEASON,
  LAB_SEASON_OPTIONS,
} from '../../../lib/cecchinoLabApi'
import { AdminHttpError } from '../../../lib/api'
import { adminLogout, getAdminSession } from '../../../lib/adminAuthApi'
import { AdminLoginDialog } from './AdminLoginDialog'
import { CecchinoRunV2DetailPanel } from './CecchinoRunV2DetailPanel'
import { RunV2Stat } from './RunV2Stat'

type Props = { refreshKey?: number }
type ConfirmMode = 'full' | 'pilot' | null

const POLL_MS = 2000
const PILOT_MAX_MATCHES = 50

function formatDateRange(start: string | null | undefined, end: string | null | undefined): string {
  if (!start && !end) return '—'
  const a = start ? formatRunV2Date(start) : '—'
  const b = end ? formatRunV2Date(end) : '—'
  return `${a} → ${b}`
}

export function CecchinoRunV2Section({ refreshKey = 0 }: Props) {
  const [season, setSeason] = useState('')
  const [preflight, setPreflight] = useState<CecchinoRunV2Preflight | null>(null)
  const [preflightLoading, setPreflightLoading] = useState(false)
  const [runs, setRuns] = useState<CecchinoRunV2[]>([])
  const [activeRun, setActiveRun] = useState<CecchinoRunV2 | null>(null)
  const [openRun, setOpenRun] = useState<CecchinoRunV2 | null>(null)
  const [confirmMode, setConfirmMode] = useState<ConfirmMode>(null)
  const [busy, setBusy] = useState(false)
  const [exportingId, setExportingId] = useState<number | null>(null)
  const [blockedBy, setBlockedBy] = useState<{ runId: number; stale: boolean } | null>(null)
  const [authenticated, setAuthenticated] = useState(false)
  // Azione di controllo rifiutata con 401: viene rieseguita dopo il login.
  const [pendingAction, setPendingAction] = useState<(() => Promise<void>) | null>(null)

  useEffect(() => {
    void getAdminSession()
      .then((s) => setAuthenticated(s.authenticated))
      .catch(() => setAuthenticated(false))
  }, [refreshKey])

  /** True se l'errore e' una sessione admin mancante: apre il login e
   *  memorizza l'azione da ripetere. */
  const handledAsAuthPrompt = (e: unknown, retry: () => Promise<void>): boolean => {
    if (!(e instanceof AdminHttpError) || e.status !== 401) return false
    setAuthenticated(false)
    setPendingAction(() => retry)
    return true
  }

  const loadRuns = useCallback(async () => {
    try {
      const items = await listRunsV2()
      setRuns(items)
      const live = items.find((r) => isRunV2Active(r))
      setActiveRun(live ?? null)
      setOpenRun((prev) =>
        prev ? (items.find((r) => r.run_id === prev.run_id) ?? prev) : prev,
      )
    } catch (e) {
      if (handledAsAuthPrompt(e, () => loadRuns())) return
      toast.error(e instanceof Error ? e.message : 'Errore caricamento RUN V2')
    }
  }, [])

  const loadPreflight = useCallback(async (seasonLabel: string) => {
    if (!seasonLabel) {
      setPreflight(null)
      return
    }
    setPreflightLoading(true)
    try {
      const pf = await preflightRunV2(seasonLabel)
      setPreflight(pf)
    } catch (e) {
      if (handledAsAuthPrompt(e, () => loadPreflight(seasonLabel))) return
      setPreflight(null)
      toast.error(e instanceof Error ? e.message : 'Preflight stagione fallito')
    } finally {
      setPreflightLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRuns()
  }, [loadRuns, refreshKey])

  useEffect(() => {
    void loadPreflight(season)
  }, [season, loadPreflight])

  useEffect(() => {
    if (!activeRun || !isRunV2Active(activeRun)) return
    const id = window.setInterval(async () => {
      try {
        const fresh = await getRunV2(activeRun.run_id)
        setActiveRun(fresh)
        setOpenRun((prev) => (prev && prev.run_id === fresh.run_id ? fresh : prev))
        if (!isRunV2Active(fresh)) {
          void loadRuns()
          if (isRunV2Completed(fresh)) toast.success(`RUN V2 #${fresh.run_id} completata`)
          else if (fresh.status === 'failed') toast.error(`RUN V2 #${fresh.run_id} fallita`)
          else if (fresh.is_stale) {
            toast.error(
              `RUN V2 #${fresh.run_id} interrotta: nessun worker attivo, riprendibile dal checkpoint`,
            )
          }
        }
      } catch {
        /* errori di polling ignorati */
      }
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [activeRun, loadRuns])

  const seasonReady =
    Boolean(season) &&
    preflight?.status === 'ready' &&
    (preflight.matches_total ?? 0) > 0 &&
    !preflightLoading
  const canStart = seasonReady && !busy && !activeRun

  const onStart = async (mode: Exclude<ConfirmMode, null>) => {
    if (!season) {
      toast.error('Seleziona una stagione')
      return
    }
    setBusy(true)
    try {
      const run = await startRunV2(
        mode === 'pilot' ? { season, maxMatches: PILOT_MAX_MATCHES } : { season },
      )
      setActiveRun(run)
      setBlockedBy(null)
      setConfirmMode(null)
      toast.success(
        mode === 'pilot'
          ? `RUN V2 pilota avviata (#${run.run_id}) — ${season}`
          : `RUN V2 completa avviata (#${run.run_id}) — ${season}`,
      )
      void loadRuns()
    } catch (e) {
      if (handledAsAuthPrompt(e, () => onStart(mode))) {
        setConfirmMode(null)
      } else if (e instanceof RunV2ApiError && e.code === 'stale_active_run') {
        const runId = Number(e.details.run_id)
        setBlockedBy({ runId, stale: true })
        setConfirmMode(null)
        toast.error(e.message)
        void loadRuns()
      } else if (e instanceof RunV2ApiError && e.code === 'duplicate_active_run') {
        setBlockedBy({ runId: Number(e.details.run_id), stale: false })
        setConfirmMode(null)
        toast.error(e.message)
        void loadRuns()
      } else {
        toast.error(e instanceof Error ? e.message : 'Avvio RUN V2 fallito')
      }
    } finally {
      setBusy(false)
    }
  }

  const onResume = async (runId: number) => {
    try {
      const run = await resumeRunV2(runId)
      setActiveRun(run)
      setBlockedBy(null)
      toast.success(`RUN V2 #${runId} ripresa dal checkpoint`)
      void loadRuns()
    } catch (e) {
      if (handledAsAuthPrompt(e, () => onResume(runId))) return
      toast.error(e instanceof Error ? e.message : 'Resume fallito')
    }
  }

  const onCancel = async (runId: number) => {
    try {
      await cancelRunV2(runId)
      setBlockedBy(null)
      toast.message(`RUN V2 #${runId} annullata`)
      void loadRuns()
    } catch (e) {
      if (handledAsAuthPrompt(e, () => onCancel(runId))) return
      toast.error(e instanceof Error ? e.message : 'Annullamento fallito')
    }
  }

  const onExportFull = async (runId: number) => {
    setExportingId(runId)
    try {
      await downloadRunV2Export(runId, 'FULL.csv')
      toast.success(`Export FULL avviato (RUN V2 #${runId})`)
    } catch (e) {
      if (handledAsAuthPrompt(e, () => onExportFull(runId))) return
      toast.error(e instanceof Error ? e.message : 'Export FULL fallito')
    } finally {
      setExportingId(null)
    }
  }

  const blockedRun = blockedBy ? runs.find((r) => r.run_id === blockedBy.runId) : undefined
  const pct = Math.min(100, Math.max(0, Number(activeRun?.progress_pct ?? 0)))

  return (
    <div className="space-y-4 border-t px-4 pb-6 pt-6 sm:px-6" style={{ borderColor: 'var(--lab-border)' }}>
      <section className="lab-card rounded-xl p-4" data-testid="run-v2-section">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div
              className="text-xs font-semibold uppercase tracking-[0.2em]"
              style={{ color: 'var(--lab-cyan)' }}
            >
              Cecchino RUN V2
            </div>
            <h3 className="mt-1 text-lg font-semibold">Run per stagione</h3>
            <p className="mt-1 max-w-2xl text-sm" style={{ color: 'var(--lab-muted)' }}>
              Seleziona una stagione, verifica i dati, poi lancia pilota o run completa. Motore
              V2 indipendente dalle Scansioni storiche V1. Pattern Lab V1 non collegato.
            </p>
          </div>
          <div
            className="rounded-lg border px-3 py-2 text-xs"
            style={{ borderColor: 'var(--lab-border)' }}
          >
            <div>
              <span className="font-semibold">Perimetro:</span> stagione selezionata
            </div>
            <div>
              <span className="font-semibold">Pattern Lab V1:</span> non collegato
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-sm" data-testid="run-v2-season-label">
            Stagione
            <select
              className="lab-input mt-1 block min-w-[10rem] rounded-md px-3 py-2"
              value={season}
              data-testid="run-v2-season-select"
              onChange={(e) => {
                setSeason(e.target.value)
                setPreflight(null)
              }}
            >
              <option value="">Seleziona stagione…</option>
              {LAB_SEASON_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="lab-btn rounded-md px-4 py-2 text-sm font-medium"
            data-testid="run-v2-preflight"
            disabled={!season || preflightLoading}
            onClick={() => void loadPreflight(season)}
          >
            {preflightLoading ? 'Verifica…' : 'Verifica dati'}
          </button>
          <button
            type="button"
            className="lab-btn rounded-md px-4 py-2 text-sm font-medium"
            data-testid="run-v2-start-pilot"
            disabled={!canStart}
            onClick={() => setConfirmMode('pilot')}
          >
            Run pilota — {PILOT_MAX_MATCHES} match
          </button>
          <button
            type="button"
            className="lab-btn rounded-md px-4 py-2 text-sm font-semibold"
            style={{ outline: '1px solid var(--lab-cyan)' }}
            data-testid="run-v2-start-full"
            disabled={!canStart}
            onClick={() => setConfirmMode('full')}
          >
            Avvia RUN V2 completa
          </button>
          {activeRun && (
            <span className="text-xs" style={{ color: 'var(--lab-muted)' }}>
              Una RUN V2 è già in corso (#{activeRun.run_id}).
            </span>
          )}
          {authenticated && (
            <span
              className="ml-auto flex items-center gap-2 text-xs"
              style={{ color: 'var(--lab-muted)' }}
              data-testid="run-v2-admin-session"
            >
              Sessione admin attiva
              <button
                type="button"
                className="underline"
                onClick={() => {
                  void adminLogout()
                    .then(() => setAuthenticated(false))
                    .catch(() => setAuthenticated(false))
                }}
              >
                Esci
              </button>
            </span>
          )}
        </div>

        {season && (
          <div
            className="mt-4 rounded-lg border p-3 text-sm"
            style={{ borderColor: 'var(--lab-border)' }}
            data-testid="run-v2-preflight-panel"
          >
            {preflightLoading && !preflight ? (
              <p style={{ color: 'var(--lab-muted)' }}>Verifica dati stagione…</p>
            ) : preflight ? (
              <div className="grid gap-1 sm:grid-cols-2">
                <div>
                  <span className="font-semibold">Stagione:</span> {preflight.season_label}
                </div>
                <div>
                  <span className="font-semibold">Match disponibili:</span>{' '}
                  {preflight.matches_total}
                </div>
                <div>
                  <span className="font-semibold">Competizioni:</span>{' '}
                  {preflight.competitions_count}
                  {preflight.competitions.length
                    ? ` (${preflight.competitions.slice(0, 8).join(', ')}${
                        preflight.competitions.length > 8 ? '…' : ''
                      })`
                    : ''}
                </div>
                <div>
                  <span className="font-semibold">Intervallo date:</span>{' '}
                  {formatDateRange(preflight.date_range?.start, preflight.date_range?.end)}
                </div>
                <div>
                  <span className="font-semibold">Dataset:</span> {preflight.datasets_count}
                </div>
                <div>
                  <span className="font-semibold">Stato:</span> {preflight.status}
                </div>
                {preflight.status !== 'ready' && (
                  <p className="sm:col-span-2 text-amber-200">
                    {preflight.blocking_anomalies?.[0]?.message ||
                      'Stagione non pronta per una RUN V2.'}
                  </p>
                )}
              </div>
            ) : (
              <p style={{ color: 'var(--lab-muted)' }}>
                Seleziona una stagione e verifica i dati prima di avviare.
              </p>
            )}
          </div>
        )}

        {blockedBy && (
          <div
            className="mt-4 rounded-lg border p-3 text-sm"
            style={{ borderColor: blockedBy.stale ? '#fcd34d' : 'var(--lab-border)' }}
            data-testid="run-v2-blocked-banner"
          >
            {blockedBy.stale ? (
              <>
                <p className="font-semibold text-amber-200">
                  RUN V2 #{blockedBy.runId} interrotta
                </p>
                <p className="mt-1" style={{ color: 'var(--lab-muted)' }}>
                  Risulta attiva sul database ma nessun worker la sta elaborando, tipicamente
                  dopo un riavvio del backend. I match già processati sono salvati
                  {blockedRun
                    ? `: ${blockedRun.matches_processed}/${blockedRun.matches_total}`
                    : ''}
                  . Riprendila dal checkpoint oppure annullala per avviarne una nuova.
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="lab-btn rounded-md px-3 py-1.5 text-sm font-semibold"
                    data-testid="run-v2-blocked-resume"
                    onClick={() => void onResume(blockedBy.runId)}
                  >
                    Riprendi RUN #{blockedBy.runId}
                  </button>
                  <button
                    type="button"
                    className="lab-btn rounded-md px-3 py-1.5 text-sm"
                    data-testid="run-v2-blocked-cancel"
                    onClick={() => void onCancel(blockedBy.runId)}
                  >
                    Annulla RUN #{blockedBy.runId}
                  </button>
                </div>
              </>
            ) : (
              <p style={{ color: 'var(--lab-muted)' }}>
                RUN V2 #{blockedBy.runId} è in esecuzione: attendere il completamento prima di
                avviarne un&apos;altra.
              </p>
            )}
          </div>
        )}
      </section>

      {activeRun && (
        <section className="lab-card rounded-xl p-4" data-testid="run-v2-active-panel">
          <h4 className="font-semibold">
            RUN V2 #{activeRun.run_id} — {runV2StatusLabel(activeRun.effective_status)}{' '}
            <span className="text-sm font-normal" style={{ color: 'var(--lab-muted)' }}>
              ({runV2ScopeLabel(activeRun)})
            </span>
          </h4>
          <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            {activeRun.run_version}
            {activeRun.season_label ? ` · ${activeRun.season_label}` : ''} · creata il{' '}
            {formatRunV2Date(activeRun.created_at)}
            {activeRun.heartbeat_at
              ? ` · heartbeat ${formatRunV2Date(activeRun.heartbeat_at)}`
              : ''}
            {activeRun.worker_alive ? ' · worker attivo' : ' · worker non attivo'}
          </p>
          <div className="mt-3 h-2 w-full overflow-hidden rounded bg-black/30">
            <div
              className="h-full transition-all"
              style={{ width: `${pct}%`, background: 'var(--lab-cyan)' }}
            />
          </div>
          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <RunV2Stat label="Stagione" value={activeRun.season_label || '—'} />
            <RunV2Stat
              label="Processati"
              value={`${activeRun.matches_processed}/${activeRun.matches_total}`}
            />
            <RunV2Stat label="Progresso" value={`${activeRun.progress_pct ?? 0}%`} />
            <RunV2Stat
              label="Leakage violations"
              value={String(activeRun.leakage_violations)}
              tone={activeRun.leakage_violations > 0 ? 'danger' : 'ok'}
            />
            <RunV2Stat label="Market rows" value={String(activeRun.market_rows_written)} />
            <RunV2Stat label="Errori" value={String(activeRun.matches_error)} />
            <RunV2Stat
              label="Heartbeat age"
              value={
                activeRun.heartbeat_age_seconds != null
                  ? `${activeRun.heartbeat_age_seconds}s`
                  : '—'
              }
            />
            <RunV2Stat
              label="Worker"
              value={activeRun.worker_alive ? 'vivo' : 'assente'}
              tone={activeRun.worker_alive ? 'ok' : 'danger'}
            />
          </div>
          {activeRun.current_competition && (
            <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
              Competizione corrente: {activeRun.current_competition}
            </p>
          )}
          {Array.isArray(activeRun.warnings) && activeRun.warnings.length > 0 && (
            <p className="mt-2 text-xs text-amber-200">Warning: {activeRun.warnings.length}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {activeRun.can_cancel && (
              <button
                type="button"
                className="lab-btn rounded-md px-3 py-1.5 text-sm"
                onClick={() => void onCancel(activeRun.run_id)}
              >
                Annulla
              </button>
            )}
          </div>
        </section>
      )}

      <section className="lab-card rounded-xl p-4">
        <h4 className="font-semibold">Storico RUN V2</h4>
        <div className="mt-3 overflow-x-auto">
          <table className="lab-table w-full text-sm">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Stagione</th>
                <th>Creata</th>
                <th>Scope</th>
                <th>Stato</th>
                <th>Progresso</th>
                <th>Leakage</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id} data-testid={`run-v2-row-${r.run_id}`}>
                  <td>{r.run_id}</td>
                  <td>{r.season_label || '—'}</td>
                  <td>{formatRunV2Date(r.created_at)}</td>
                  <td>{runV2ScopeLabel(r)}</td>
                  <td>
                    {runV2StatusLabel(r.effective_status)}
                    {r.is_stale && (
                      <span
                        className="ml-1 text-xs text-amber-200"
                        data-testid={`run-v2-stale-badge-${r.run_id}`}
                      >
                        worker non attivo
                      </span>
                    )}
                  </td>
                  <td>
                    {r.matches_processed}/{r.matches_total} ({r.progress_pct ?? 0}%)
                  </td>
                  <td>{r.leakage_violations}</td>
                  <td className="space-x-3 whitespace-nowrap">
                    <button
                      type="button"
                      className="font-medium text-[var(--lab-cyan)] underline-offset-2 hover:underline"
                      data-testid={`run-v2-open-${r.run_id}`}
                      onClick={() => setOpenRun(r)}
                    >
                      Apri
                    </button>
                    <Link
                      to={`/cecchino-lab?tab=run_v2&run_v2_id=${r.run_id}`}
                      className="font-medium text-[var(--lab-cyan)] underline-offset-2 hover:underline"
                      data-testid={`run-v2-analyze-${r.run_id}`}
                    >
                      Analizza
                    </Link>
                    {isRunV2Completed(r) && (
                      <button
                        type="button"
                        className="font-medium text-[var(--lab-cyan)] underline-offset-2 hover:underline"
                        data-testid={`run-v2-export-full-${r.run_id}`}
                        disabled={exportingId === r.run_id}
                        onClick={() => void onExportFull(r.run_id)}
                      >
                        {exportingId === r.run_id ? 'Export…' : 'Esporta FULL'}
                      </button>
                    )}
                    {r.can_resume && (
                      <button
                        type="button"
                        className="font-medium text-[var(--lab-cyan)] underline-offset-2 hover:underline"
                        data-testid={`run-v2-resume-${r.run_id}`}
                        onClick={() => void onResume(r.run_id)}
                      >
                        Riprendi
                      </button>
                    )}
                    {r.can_cancel && (
                      <button
                        type="button"
                        className="font-medium text-[var(--lab-cyan)] underline-offset-2 hover:underline"
                        data-testid={`run-v2-cancel-${r.run_id}`}
                        onClick={() => void onCancel(r.run_id)}
                      >
                        Annulla
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!runs.length && (
                <tr>
                  <td colSpan={8} style={{ color: 'var(--lab-muted)' }}>
                    Nessuna RUN V2 registrata.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {openRun && (
        <CecchinoRunV2DetailPanel run={openRun} onClose={() => setOpenRun(null)} />
      )}

      {pendingAction && (
        <AdminLoginDialog
          onClose={() => setPendingAction(null)}
          onSuccess={() => {
            const retry = pendingAction
            setPendingAction(null)
            setAuthenticated(true)
            void retry()
          }}
        />
      )}

      {confirmMode && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="lab-card max-w-md rounded-xl p-5">
            <h3 className="text-lg font-semibold">
              {confirmMode === 'pilot' ? 'Conferma RUN V2 pilota' : 'Conferma RUN V2 completa'}
            </h3>
            <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
              {confirmMode === 'pilot' ? (
                <>
                  Avviare la run pilota sui primi <strong>{PILOT_MAX_MATCHES}</strong> match
                  della stagione <strong>{season || DEFAULT_HISTORICAL_SEASON}</strong>? Serve
                  solo come prova tecnica.
                </>
              ) : (
                <>
                  Avviare la RUN V2 completa sulla stagione{' '}
                  <strong>{season || DEFAULT_HISTORICAL_SEASON}</strong>
                  {preflight?.matches_total != null
                    ? ` (${preflight.matches_total} match)`
                    : ''}
                  ? L&apos;elaborazione gira in background.
                </>
              )}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="lab-btn rounded-md px-3 py-2 text-sm"
                onClick={() => setConfirmMode(null)}
              >
                Annulla
              </button>
              <button
                type="button"
                className="lab-btn rounded-md px-3 py-2 text-sm font-semibold"
                data-testid="run-v2-confirm-start"
                disabled={busy || !season}
                onClick={() => void onStart(confirmMode)}
              >
                Conferma avvio
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
