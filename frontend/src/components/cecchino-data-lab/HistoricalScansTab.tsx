import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import {
  DEFAULT_HISTORICAL_SEASON,
  HISTORICAL_SCAN_BALANCED_ELIGIBLE_PER_COMP,
  HISTORICAL_SCAN_PILOT_MAX_MATCHES,
  LAB_SEASON_OPTIONS,
  cancelHistoricalScan,
  downloadHistoricalScanReport,
  getHistoricalScan,
  historicalScanScopeLabel,
  historicalScanStatusLabel,
  isHistoricalScanActive,
  listHistoricalScans,
  preflightHistoricalScan,
  resumeHistoricalScan,
  startHistoricalScan,
  type HistoricalReportMode,
  type HistoricalReportModule,
  type HistoricalScanPreflight,
  type HistoricalScanRun,
} from '../../lib/cecchinoLabApi'

type Props = { refreshKey: number }
type ConfirmMode = 'balanced' | 'pilot' | 'full' | null

const REPORT_MENU: Array<{
  mode: HistoricalReportMode
  module?: HistoricalReportModule
  label: string
  recommended?: boolean
  needsCompetition?: boolean
  sizeWarning?: boolean
}> = [
  { mode: 'ai_summary', label: 'Sintesi per ChatGPT', recommended: true },
  { mode: 'competition', label: 'Dettaglio per campionato', needsCompetition: true },
  { mode: 'module', module: 'signals', label: 'Dettaglio Segnali A–F' },
  { mode: 'module', module: 'balance', label: 'Dettaglio Balance / Equilibrio' },
  { mode: 'module', module: 'goal_intensity', label: 'Dettaglio Intensità Goal' },
  { mode: 'module', module: 'purchasability', label: 'Dettaglio Acquistabilità' },
  { mode: 'module', module: 'markets', label: 'Dettaglio mercati' },
  {
    mode: 'full_archive',
    label: 'Archivio tecnico completo',
    sizeWarning: true,
  },
]

export function HistoricalScansTab({ refreshKey }: Props) {
  const [season, setSeason] = useState(DEFAULT_HISTORICAL_SEASON)
  const [preflight, setPreflight] = useState<HistoricalScanPreflight | null>(null)
  const [preflightLoading, setPreflightLoading] = useState(false)
  const [runs, setRuns] = useState<HistoricalScanRun[]>([])
  const [activeRun, setActiveRun] = useState<HistoricalScanRun | null>(null)
  const [confirmMode, setConfirmMode] = useState<ConfirmMode>(null)
  const [busy, setBusy] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)
  const [techOpen, setTechOpen] = useState(false)
  const [reportCompetition, setReportCompetition] = useState('')
  const [downloadBusy, setDownloadBusy] = useState(false)

  const competitions = useMemo(() => {
    const fromPreflight = preflight?.competitions_found ?? []
    const fromSummary = Array.isArray(activeRun?.summary?.progress_detail)
      ? []
      : []
    const fromPolicy =
      (activeRun?.module_policy?.competitions_total as number | undefined) != null
        ? fromPreflight
        : fromPreflight
    return Array.from(new Set([...fromPolicy, ...fromSummary])).filter(Boolean)
  }, [preflight, activeRun])

  const competitionOptions = useMemo(() => {
    if (preflight?.competitions_found?.length) return preflight.competitions_found
    return competitions
  }, [preflight, competitions])

  const loadRuns = useCallback(async () => {
    try {
      const items = await listHistoricalScans(season)
      setRuns(items)
      const running = items.find((r) => isHistoricalScanActive(r.status))
      if (running) setActiveRun(running)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Errore caricamento run')
    }
  }, [season])

  useEffect(() => {
    void loadRuns()
  }, [loadRuns, refreshKey])

  useEffect(() => {
    if (!activeRun || !isHistoricalScanActive(activeRun.status)) return
    const id = window.setInterval(async () => {
      try {
        const fresh = await getHistoricalScan(activeRun.id)
        setActiveRun(fresh)
        if (!isHistoricalScanActive(fresh.status)) {
          void loadRuns()
          if (fresh.status.startsWith('completed')) {
            toast.success(
              fresh.is_partial_run
                ? 'Scansione pilota completata'
                : 'Scansione storica completata',
            )
          } else if (fresh.status === 'failed') {
            toast.error('Scansione fallita')
          }
        }
      } catch {
        /* ignore polling errors */
      }
    }, 2000)
    return () => window.clearInterval(id)
  }, [activeRun, loadRuns])

  useEffect(() => {
    if (competitionOptions.length && !reportCompetition) {
      setReportCompetition(competitionOptions[0] ?? '')
    }
  }, [competitionOptions, reportCompetition])

  const onPreflight = async () => {
    setPreflightLoading(true)
    try {
      const pf = await preflightHistoricalScan(season)
      setPreflight(pf)
      toast.message(`Preflight: ${historicalScanStatusLabel(pf.status)}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Preflight fallito')
    } finally {
      setPreflightLoading(false)
    }
  }

  const onStart = async (mode: Exclude<ConfirmMode, null>) => {
    setBusy(true)
    try {
      const run = await startHistoricalScan(
        season,
        mode === 'balanced'
          ? {
              pilotStrategy: 'eligible_per_competition',
              eligiblePerCompetition: HISTORICAL_SCAN_BALANCED_ELIGIBLE_PER_COMP,
            }
          : mode === 'pilot'
            ? { maxMatches: HISTORICAL_SCAN_PILOT_MAX_MATCHES, pilotStrategy: 'max_matches' }
            : { maxMatches: null },
      )
      setActiveRun(run)
      setConfirmMode(null)
      setTechOpen(false)
      toast.success(
        mode === 'balanced'
          ? `Pilota bilanciato avviato (#${run.id})`
          : mode === 'pilot'
            ? `Test tecnico avviato (#${run.id})`
            : `Scansione completa avviata (#${run.id})`,
      )
      void loadRuns()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Avvio fallito')
    } finally {
      setBusy(false)
    }
  }

  const onDownloadReport = async (
    mode: HistoricalReportMode,
    module?: HistoricalReportModule,
    needsCompetition?: boolean,
  ) => {
    if (!activeRun) return
    if (needsCompetition && !reportCompetition) {
      toast.error('Seleziona un campionato')
      return
    }
    setDownloadBusy(true)
    try {
      await downloadHistoricalScanReport(activeRun.id, {
        mode,
        module,
        competition: needsCompetition ? reportCompetition : undefined,
      })
      toast.success(`Download avviato: ${mode}`)
      setReportOpen(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Download fallito')
    } finally {
      setDownloadBusy(false)
    }
  }

  const blocked = preflight?.status === 'blocked'
  const canStart =
    preflight &&
    (preflight.status === 'ready' || preflight.status === 'ready_with_warnings') &&
    !busy

  const pct = activeRun?.progress_pct ?? 0
  const pd = activeRun?.progress_detail

  const summaryForUi = useMemo(() => {
    if (!activeRun?.summary) return null
    const s = { ...activeRun.summary }
    delete s.real_profit_1u
    delete s.synthetic_profit_1u
    return s
  }, [activeRun?.summary])

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <section className="lab-card rounded-xl p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Scansioni storiche</h2>
            <p className="mt-1 text-sm" style={{ color: 'var(--lab-muted)' }}>
              Replay pre-match offline sulla stagione selezionata. Nessuna chiamata esterna.
            </p>
          </div>
          <div className="rounded-lg border px-3 py-2 text-xs" style={{ borderColor: 'var(--lab-border)' }}>
            <div>
              <span className="font-semibold">Storico:</span> Bet365
            </div>
            <div>
              <span className="font-semibold">Cecchino Today operativo:</span> Betfair, invariato
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            Stagione
            <select
              className="lab-input mt-1 block min-w-[10rem] rounded-md px-3 py-2"
              value={season}
              onChange={(e) => {
                setSeason(e.target.value)
                setPreflight(null)
              }}
            >
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
            onClick={() => void onPreflight()}
            disabled={preflightLoading}
          >
            {preflightLoading ? 'Verifica…' : 'Verifica dati'}
          </button>
          <button
            type="button"
            className="lab-btn rounded-md px-4 py-2 text-sm font-semibold"
            disabled={!canStart}
            onClick={() => setConfirmMode('full')}
            style={{ outline: '1px solid var(--lab-cyan)' }}
          >
            Scansione completa
          </button>
          <div className="relative">
            <button
              type="button"
              className="lab-btn rounded-md px-4 py-2 text-sm font-medium opacity-80"
              disabled={!canStart}
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
                  Diagnostica — non necessarie per la scansione ordinaria
                </p>
                <ul className="space-y-1 text-sm">
                  <li>
                    <button
                      type="button"
                      className="w-full rounded px-2 py-1.5 text-left hover:bg-white/10"
                      disabled={!canStart}
                      onClick={() => {
                        setTechOpen(false)
                        setConfirmMode('pilot')
                      }}
                    >
                      Test tecnico — prime {HISTORICAL_SCAN_PILOT_MAX_MATCHES} partite
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      className="w-full rounded px-2 py-1.5 text-left hover:bg-white/10"
                      disabled={!canStart}
                      onClick={() => {
                        setTechOpen(false)
                        setConfirmMode('balanced')
                      }}
                    >
                      Pilota bilanciato — {HISTORICAL_SCAN_BALANCED_ELIGIBLE_PER_COMP}{' '}
                      eleggibili/campionato
                    </button>
                  </li>
                </ul>
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-3 text-xs">
          <LegendDot className="lab-quote-real" label="Quota Bet365 reale" />
          <LegendDot className="lab-quote-derived" label="Quota derivata" />
          <LegendDot className="lab-quote-na" label="Quota non disponibile" />
        </div>
      </section>

      {preflight && (
        <section className="lab-card rounded-xl p-4">
          <h3 className="font-semibold">
            Preflight — {historicalScanStatusLabel(preflight.status)}
          </h3>
          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Campionati" value={String(preflight.competitions_found?.length ?? 0)} />
            <Stat label="Partite" value={String(preflight.matches_total ?? 0)} />
            <Stat label="FT" value={String(preflight.matches_with_ft ?? '—')} />
            <Stat label="HT" value={String(preflight.matches_with_ht ?? '—')} />
            <Stat
              label="Bet365 1X2 closing"
              value={String(preflight.bet365_1x2_closing_coverage ?? '—')}
            />
            <Stat
              label="Bet365 1X2 pre"
              value={String(preflight.bet365_1x2_pre_coverage ?? '—')}
            />
            <Stat
              label="O/U 2.5 closing"
              value={String(preflight.bet365_ou25_closing_coverage ?? '—')}
            />
            <Stat label="O/U 2.5 pre" value={String(preflight.bet365_ou25_pre_coverage ?? '—')} />
          </div>
          {preflight.quote_counts && (
            <div className="mt-3 flex flex-wrap gap-3 text-sm">
              <span className="lab-quote-real rounded px-2 py-1">
                Reali: {preflight.quote_counts.real}
              </span>
              <span className="lab-quote-derived rounded px-2 py-1">
                Derivate: {preflight.quote_counts.derived}
              </span>
              <span className="lab-quote-na rounded px-2 py-1">
                N/D: {preflight.quote_counts.not_available}
              </span>
            </div>
          )}
          {!!preflight.blocking_anomalies?.length && (
            <ul className="mt-3 list-disc pl-5 text-sm text-red-300">
              {preflight.blocking_anomalies.map((b) => (
                <li key={b.code}>{b.message}</li>
              ))}
            </ul>
          )}
          {!!preflight.warnings?.length && (
            <ul className="mt-3 list-disc pl-5 text-sm text-amber-200">
              {preflight.warnings.map((w) => (
                <li key={w.code}>{w.message}</li>
              ))}
            </ul>
          )}
          {blocked && (
            <p className="mt-3 text-sm text-red-300">
              Stato blocked: avvio scansione non consentito finché i problemi strutturali non sono
              risolti.
            </p>
          )}
        </section>
      )}

      {activeRun && (
        <section className="lab-card rounded-xl p-4">
          <h3 className="font-semibold">
            Run #{activeRun.id} — {historicalScanStatusLabel(activeRun.status)}{' '}
            <span className="text-sm font-normal" style={{ color: 'var(--lab-muted)' }}>
              ({historicalScanScopeLabel(activeRun)})
            </span>
          </h3>
          {activeRun.is_partial_run && (
            <p className="mt-1 text-xs text-amber-200">
              Run parziale / pilota: non confondere con il report stagione completa.
            </p>
          )}
          <div className="mt-3 h-2 w-full overflow-hidden rounded bg-black/30">
            <div
              className="h-full transition-all"
              style={{
                width: `${Math.min(100, Math.max(0, pct))}%`,
                background: 'var(--lab-cyan)',
              }}
            />
          </div>
          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
            {pd ? (
              <>
                <Stat
                  label="Campionati"
                  value={`${pd.competitions_completed ?? 0}/${pd.competitions_total ?? '—'}`}
                />
                <Stat
                  label="Eleggibili / target"
                  value={`${pd.eligible_collected ?? activeRun.matches_eligible_core}/${pd.eligible_target ?? '—'}`}
                />
                <Stat
                  label="Eleggibili campionato corrente"
                  value={`${pd.eligible_in_current_competition ?? '—'}/${pd.eligible_per_competition_target ?? '—'}`}
                />
                <Stat
                  label="Processate totali"
                  value={String(pd.matches_processed ?? activeRun.matches_processed)}
                />
                <Stat label="Escluse" value={String(pd.matches_excluded ?? activeRun.matches_excluded)} />
                <Stat label="Errori" value={String(pd.matches_error ?? activeRun.matches_error)} />
              </>
            ) : (
              <>
                <Stat
                  label="Processate"
                  value={`${activeRun.matches_processed}/${activeRun.matches_total}`}
                />
                <Stat label="Eleggibili" value={String(activeRun.matches_eligible_core)} />
                <Stat label="Escluse" value={String(activeRun.matches_excluded)} />
                <Stat label="Errori" value={String(activeRun.matches_error)} />
              </>
            )}
          </div>
          {(activeRun.current_competition || pd?.current_competition) && (
            <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
              Campionato corrente: {activeRun.current_competition ?? pd?.current_competition}
            </p>
          )}
          {(activeRun.source_git_commit || activeRun.source_revision_status) && (
            <p className="mt-2 text-xs" style={{ color: 'var(--lab-muted)' }}>
              Revisione: {activeRun.source_git_commit ?? 'sconosciuta'}
              {activeRun.source_git_commit_source
                ? ` (${activeRun.source_git_commit_source})`
                : ''}{' '}
              — {activeRun.source_revision_status ?? 'n/d'}
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {isHistoricalScanActive(activeRun.status) && (
              <button
                type="button"
                className="lab-btn rounded-md px-3 py-1.5 text-sm"
                onClick={() =>
                  void cancelHistoricalScan(activeRun.id).then(setActiveRun).catch((e) =>
                    toast.error(e instanceof Error ? e.message : 'Cancel fallito'),
                  )
                }
              >
                Annulla
              </button>
            )}
            {(activeRun.status === 'failed' || activeRun.status === 'cancelled') && (
              <button
                type="button"
                className="lab-btn rounded-md px-3 py-1.5 text-sm"
                onClick={() =>
                  void resumeHistoricalScan(activeRun.id).then(setActiveRun).catch((e) =>
                    toast.error(e instanceof Error ? e.message : 'Resume fallito'),
                  )
                }
              >
                Riprendi
              </button>
            )}
            {activeRun.status.startsWith('completed') && (
              <div className="relative">
                <button
                  type="button"
                  className="lab-btn rounded-md px-3 py-1.5 text-sm font-semibold"
                  onClick={() => setReportOpen((v) => !v)}
                  disabled={downloadBusy}
                >
                  {downloadBusy ? 'Download…' : 'Scarica report'}
                </button>
                {reportOpen && (
                  <div
                    className="absolute left-0 z-20 mt-1 min-w-[18rem] rounded-md border p-2 shadow-lg"
                    style={{
                      background: 'var(--lab-card, #0f172a)',
                      borderColor: 'var(--lab-border)',
                    }}
                  >
                    <p className="mb-2 text-xs" style={{ color: 'var(--lab-muted)' }}>
                      Tipo report — consigliato: Sintesi per ChatGPT
                    </p>
                    {competitionOptions.length > 0 && (
                      <label className="mb-2 block text-xs">
                        Campionato
                        <select
                          className="lab-input mt-1 block w-full rounded px-2 py-1 text-sm"
                          value={reportCompetition}
                          onChange={(e) => setReportCompetition(e.target.value)}
                        >
                          {competitionOptions.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                    <ul className="space-y-1 text-sm">
                      {REPORT_MENU.map((item) => (
                        <li key={`${item.mode}-${item.module ?? 'x'}`}>
                          <button
                            type="button"
                            className="w-full rounded px-2 py-1.5 text-left hover:bg-white/10"
                            disabled={downloadBusy}
                            onClick={() =>
                              void onDownloadReport(
                                item.mode,
                                item.module,
                                item.needsCompetition,
                              )
                            }
                          >
                            {item.label}
                            {item.recommended ? ' ★' : ''}
                            {item.sizeWarning ? (
                              <span className="mt-0.5 block text-[11px] text-amber-200">
                                Archivio tecnico completo — non necessario per la prima analisi
                                ChatGPT. Può essere molto grande.
                              </span>
                            ) : null}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
          {summaryForUi && (
            <pre
              className="mt-3 max-h-48 overflow-auto rounded-md p-3 text-xs"
              style={{ background: 'rgba(0,0,0,0.25)' }}
            >
              {JSON.stringify(summaryForUi, null, 2)}
            </pre>
          )}
        </section>
      )}

      <section className="lab-card rounded-xl p-4">
        <h3 className="font-semibold">Storico run</h3>
        <div className="mt-3 overflow-x-auto">
          <table className="lab-table w-full text-sm">
            <thead>
              <tr>
                <th>ID</th>
                <th>Stagione</th>
                <th>Scope</th>
                <th>Stato</th>
                <th>Progresso</th>
                <th>Eleggibili</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.season_label}</td>
                  <td>{historicalScanScopeLabel(r)}</td>
                  <td>{historicalScanStatusLabel(r.status)}</td>
                  <td>
                    {r.matches_processed}/{r.matches_total} ({r.progress_pct ?? 0}%)
                  </td>
                  <td>{r.matches_eligible_core}</td>
                  <td className="space-x-3 whitespace-nowrap">
                    <Link
                      to={`/cecchino-lab/historical-scans/${r.id}`}
                      className="font-medium text-[var(--lab-cyan)] underline-offset-2 hover:underline"
                    >
                      Apri analisi
                    </Link>
                    <button
                      type="button"
                      className="underline"
                      onClick={() => setActiveRun(r)}
                    >
                      Dettaglio
                    </button>
                    {r.status.startsWith('completed') && (
                      <>
                        {' · '}
                        <button
                          type="button"
                          className="underline"
                          onClick={() => {
                            setActiveRun(r)
                            setReportOpen(true)
                          }}
                        >
                          Report
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {!runs.length && (
                <tr>
                  <td colSpan={7} style={{ color: 'var(--lab-muted)' }}>
                    Nessun run per questa stagione.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {confirmMode && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="lab-card max-w-md rounded-xl p-5">
            <h3 className="text-lg font-semibold">
              {confirmMode === 'balanced'
                ? 'Conferma pilota bilanciato'
                : confirmMode === 'pilot'
                  ? 'Conferma test tecnico'
                  : 'Conferma scansione completa'}
            </h3>
            <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
              {confirmMode === 'balanced' ? (
                <>
                  Avviare il pilota bilanciato ({HISTORICAL_SCAN_BALANCED_ELIGIBLE_PER_COMP}{' '}
                  eleggibili per campionato) sulla stagione <strong>{season}</strong>? Il report sarà
                  marcato come run parziale.
                </>
              ) : confirmMode === 'pilot' ? (
                <>
                  Avviare il test tecnico sulle prime{' '}
                  <strong>{HISTORICAL_SCAN_PILOT_MAX_MATCHES}</strong> partite della stagione{' '}
                  <strong>{season}</strong>? Utile solo come prova tecnica (es. Run #1).
                </>
              ) : (
                <>
                  Avviare il replay completo sulla stagione <strong>{season}</strong>? Il processo è
                  offline, può richiedere diversi minuti e non modifica Cecchino Today (Betfair).
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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border px-3 py-2" style={{ borderColor: 'var(--lab-border)' }}>
      <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>
        {label}
      </div>
      <div className="font-semibold">{value}</div>
    </div>
  )
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className={`inline-flex items-center gap-2 rounded px-2 py-1 ${className}`}>
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ background: 'currentColor' }}
      />
      {label}
    </span>
  )
}
