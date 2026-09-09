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
  resumeRunV2,
  runV2ScopeLabel,
  runV2StatusLabel,
  startRunV2,
  type CecchinoRunV2,
} from '../../../lib/cecchinoRunV2Api'
import { CecchinoRunV2DetailPanel } from './CecchinoRunV2DetailPanel'
import { RunV2Stat } from './RunV2Stat'

type Props = { refreshKey?: number }
type ConfirmMode = 'full' | 'pilot' | null

const POLL_MS = 2000
const PILOT_MAX_MATCHES = 50

export function CecchinoRunV2Section({ refreshKey = 0 }: Props) {
  const [runs, setRuns] = useState<CecchinoRunV2[]>([])
  const [activeRun, setActiveRun] = useState<CecchinoRunV2 | null>(null)
  const [openRun, setOpenRun] = useState<CecchinoRunV2 | null>(null)
  const [confirmMode, setConfirmMode] = useState<ConfirmMode>(null)
  const [busy, setBusy] = useState(false)
  const [techOpen, setTechOpen] = useState(false)
  const [exportingId, setExportingId] = useState<number | null>(null)
  const [blockedBy, setBlockedBy] = useState<{ runId: number; stale: boolean } | null>(null)

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
      toast.error(e instanceof Error ? e.message : 'Errore caricamento RUN V2')
    }
  }, [])

  useEffect(() => {
    void loadRuns()
  }, [loadRuns, refreshKey])

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

  const onStart = async (mode: Exclude<ConfirmMode, null>) => {
    setBusy(true)
    try {
      const run = await startRunV2(
        mode === 'pilot' ? { maxMatches: PILOT_MAX_MATCHES } : undefined,
      )
      setActiveRun(run)
      setBlockedBy(null)
      setConfirmMode(null)
      setTechOpen(false)
      toast.success(
        mode === 'pilot'
          ? `RUN V2 pilota avviata (#${run.run_id})`
          : `RUN V2 completa avviata (#${run.run_id})`,
      )
      void loadRuns()
    } catch (e) {
      if (e instanceof RunV2ApiError && e.code === 'stale_active_run') {
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
      toast.error(e instanceof Error ? e.message : 'Annullamento fallito')
    }
  }

  const onExportFull = async (runId: number) => {
    setExportingId(runId)
    try {
      await downloadRunV2Export(runId, 'FULL.csv')
      toast.success(`Export FULL avviato (RUN V2 #${runId})`)
    } catch (e) {
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
            <h3 className="mt-1 text-lg font-semibold">Run completa sull&apos;archivio</h3>
            <p className="mt-1 max-w-2xl text-sm" style={{ color: 'var(--lab-muted)' }}>
              Motore V2 con doppio binario quote e audit anti-leakage, indipendente dalle
              Scansioni storiche V1 qui sopra. Le analisi V1 non vengono toccate.
            </p>
          </div>
          <div
            className="rounded-lg border px-3 py-2 text-xs"
            style={{ borderColor: 'var(--lab-border)' }}
          >
            <div>
              <span className="font-semibold">Perimetro:</span> intero archivio Cecchino Lab
            </div>
            <div>
              <span className="font-semibold">Pattern Lab V1:</span> non collegato
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="lab-btn rounded-md px-4 py-2 text-sm font-semibold"
            style={{ outline: '1px solid var(--lab-cyan)' }}
            data-testid="run-v2-start-full"
            disabled={busy || Boolean(activeRun)}
            onClick={() => setConfirmMode('full')}
          >
            Avvia RUN V2 completa
          </button>
          <div className="relative">
            <button
              type="button"
              className="lab-btn rounded-md px-4 py-2 text-sm font-medium opacity-80"
              disabled={busy || Boolean(activeRun)}
              onClick={() => setTechOpen((v) => !v)}
            >
              Opzioni tecniche
            </button>
            {techOpen && (
              <div
                className="absolute left-0 z-20 mt-1 min-w-[16rem] rounded-md border p-2 shadow-lg"
                style={{
                  background: 'var(--lab-card, #0f172a)',
                  borderColor: 'var(--lab-border)',
                }}
              >
                <p className="mb-2 text-xs" style={{ color: 'var(--lab-muted)' }}>
                  Solo diagnostica: stessa logica della run completa, su meno match.
                </p>
                <button
                  type="button"
                  className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-white/10"
                  onClick={() => {
                    setTechOpen(false)
                    setConfirmMode('pilot')
                  }}
                >
                  Run pilota — primi {PILOT_MAX_MATCHES} match
                </button>
              </div>
            )}
          </div>
          {activeRun && (
            <span className="text-xs" style={{ color: 'var(--lab-muted)' }}>
              Una RUN V2 è già in corso (#{activeRun.run_id}).
            </span>
          )}
        </div>

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
            {activeRun.run_version} · creata il {formatRunV2Date(activeRun.created_at)}
          </p>
          <div className="mt-3 h-2 w-full overflow-hidden rounded bg-black/30">
            <div
              className="h-full transition-all"
              style={{ width: `${pct}%`, background: 'var(--lab-cyan)' }}
            />
          </div>
          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <RunV2Stat
              label="Processati"
              value={`${activeRun.matches_processed}/${activeRun.matches_total}`}
            />
            <RunV2Stat label="Progresso" value={`${activeRun.progress_pct ?? 0}%`} />
            <RunV2Stat label="Errori" value={String(activeRun.matches_error)} />
            <RunV2Stat
              label="Leakage violations"
              value={String(activeRun.leakage_violations)}
              tone={activeRun.leakage_violations > 0 ? 'danger' : 'ok'}
            />
          </div>
          {activeRun.current_competition && (
            <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
              Competizione corrente: {activeRun.current_competition}
            </p>
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
                <th>Creata</th>
                <th>Versione</th>
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
                  <td>{formatRunV2Date(r.created_at)}</td>
                  <td>{r.run_version}</td>
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
                  Avviare la run pilota sui primi <strong>{PILOT_MAX_MATCHES}</strong> match?
                  Serve solo come prova tecnica.
                </>
              ) : (
                <>
                  Avviare la RUN V2 sull&apos;intero archivio? L&apos;elaborazione gira in
                  background: la pagina mostra lo stato aggiornato e può essere chiusa senza
                  interrompere la run.
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
                disabled={busy}
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
