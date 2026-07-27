import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  DEFAULT_HISTORICAL_SEASON,
  LAB_SEASON_OPTIONS,
  cancelHistoricalScan,
  downloadHistoricalScanReport,
  getHistoricalScan,
  historicalScanStatusLabel,
  isHistoricalScanActive,
  listHistoricalScans,
  preflightHistoricalScan,
  resumeHistoricalScan,
  startHistoricalScan,
  type HistoricalScanPreflight,
  type HistoricalScanRun,
} from '../../lib/cecchinoLabApi'

type Props = { refreshKey: number }

export function HistoricalScansTab({ refreshKey }: Props) {
  const [season, setSeason] = useState(DEFAULT_HISTORICAL_SEASON)
  const [preflight, setPreflight] = useState<HistoricalScanPreflight | null>(null)
  const [preflightLoading, setPreflightLoading] = useState(false)
  const [runs, setRuns] = useState<HistoricalScanRun[]>([])
  const [activeRun, setActiveRun] = useState<HistoricalScanRun | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [busy, setBusy] = useState(false)

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
            toast.success('Scansione storica completata')
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

  const onStart = async () => {
    setBusy(true)
    try {
      const run = await startHistoricalScan(season)
      setActiveRun(run)
      setConfirmOpen(false)
      toast.success(`Scansione avviata (#${run.id})`)
      void loadRuns()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Avvio fallito')
    } finally {
      setBusy(false)
    }
  }

  const blocked = preflight?.status === 'blocked'
  const canStart =
    preflight &&
    (preflight.status === 'ready' || preflight.status === 'ready_with_warnings') &&
    !busy

  const pct = activeRun?.progress_pct ?? 0

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
            className="lab-btn rounded-md px-4 py-2 text-sm font-medium"
            disabled={!canStart}
            onClick={() => setConfirmOpen(true)}
          >
            Avvia scansione
          </button>
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
            Run #{activeRun.id} — {historicalScanStatusLabel(activeRun.status)}
          </h3>
          <div className="mt-3 h-2 w-full overflow-hidden rounded bg-black/30">
            <div
              className="h-full transition-all"
              style={{
                width: `${Math.min(100, Math.max(0, pct))}%`,
                background: 'var(--lab-cyan)',
              }}
            />
          </div>
          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Processate"
              value={`${activeRun.matches_processed}/${activeRun.matches_total}`}
            />
            <Stat label="Eleggibili" value={String(activeRun.matches_eligible_core)} />
            <Stat label="Escluse" value={String(activeRun.matches_excluded)} />
            <Stat label="Errori" value={String(activeRun.matches_error)} />
          </div>
          {activeRun.current_competition && (
            <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
              Campionato in elaborazione: {activeRun.current_competition}
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
              <button
                type="button"
                className="lab-btn rounded-md px-3 py-1.5 text-sm"
                onClick={() =>
                  void downloadHistoricalScanReport(activeRun.id).catch((e) =>
                    toast.error(e instanceof Error ? e.message : 'Download fallito'),
                  )
                }
              >
                Scarica report per ChatGPT
              </button>
            )}
          </div>
          {activeRun.summary && (
            <pre
              className="mt-3 max-h-48 overflow-auto rounded-md p-3 text-xs"
              style={{ background: 'rgba(0,0,0,0.25)' }}
            >
              {JSON.stringify(activeRun.summary, null, 2)}
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
                  <td>{historicalScanStatusLabel(r.status)}</td>
                  <td>
                    {r.matches_processed}/{r.matches_total} ({r.progress_pct ?? 0}%)
                  </td>
                  <td>{r.matches_eligible_core}</td>
                  <td>
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
                          onClick={() =>
                            void downloadHistoricalScanReport(r.id).catch((e) =>
                              toast.error(e instanceof Error ? e.message : 'Download fallito'),
                            )
                          }
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
                  <td colSpan={6} style={{ color: 'var(--lab-muted)' }}>
                    Nessun run per questa stagione.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {confirmOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="lab-card max-w-md rounded-xl p-5">
            <h3 className="text-lg font-semibold">Conferma scansione storica</h3>
            <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
              Avviare il replay Cecchino sulla stagione <strong>{season}</strong>? Il processo è
              offline, può richiedere diversi minuti e non modifica Cecchino Today (Betfair).
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="lab-btn rounded-md px-3 py-2 text-sm"
                onClick={() => setConfirmOpen(false)}
              >
                Annulla
              </button>
              <button
                type="button"
                className="lab-btn rounded-md px-3 py-2 text-sm font-semibold"
                disabled={busy}
                onClick={() => void onStart()}
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
