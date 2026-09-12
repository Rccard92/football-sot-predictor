import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  PATTERN_GRID_MARKET_KEYS,
  cancelPatternGridRun,
  formatRoiPct,
  getPatternGridCandidates,
  getPatternGridRun,
  isPatternGridActive,
  startPatternGridRun,
  verdictBadgeClass,
  verdictLabel,
  type PatternGridCandidate,
  type PatternGridRun,
} from '../../../lib/cecchinoPatternGridApi'
import { roiColor } from '../overview/overviewTheme'

const POLL_MS = 3000
const DEFAULT_RUN_IDS = [17, 19, 20, 21]
const STAGE_SEASON_LABELS = ['2021/22', '2022/23', '2023/24', '2024/25']

function StageCell({ result }: { result?: { status: string; roi_pct: number | null; n: number } }) {
  if (!result) {
    return <span style={{ color: 'var(--lab-muted)' }}>— non nato</span>
  }
  if (result.status === 'insufficient_sample') {
    return (
      <span style={{ color: 'var(--lab-muted)' }} title={`N=${result.n}, campione insufficiente`}>
        campione insuff. (N={result.n})
      </span>
    )
  }
  const ok = result.status === 'confirmed'
  return (
    <span
      className={`lab-badge-${ok ? 'ok' : 'err'} rounded px-1.5 py-0.5 text-xs`}
      title={`N=${result.n}`}
    >
      {ok ? '✓' : '✗'} <span style={{ color: roiColor(result.roi_pct ?? 0) }}>{formatRoiPct(result.roi_pct)}</span>
    </span>
  )
}

export function PatternGridTab() {
  const [marketKey, setMarketKey] = useState<string>('DRAW')
  const [competition, setCompetition] = useState('')
  const [activeRun, setActiveRun] = useState<PatternGridRun | null>(null)
  const [candidates, setCandidates] = useState<PatternGridCandidate[]>([])
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [starting, setStarting] = useState(false)

  const loadCandidates = useCallback(async (runId: number) => {
    setLoadingCandidates(true)
    try {
      const items = await getPatternGridCandidates(runId)
      setCandidates(items)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Errore caricamento candidati')
    } finally {
      setLoadingCandidates(false)
    }
  }, [])

  useEffect(() => {
    if (!activeRun || !isPatternGridActive(activeRun)) return
    const id = window.setInterval(async () => {
      try {
        const fresh = await getPatternGridRun(activeRun.id)
        setActiveRun(fresh)
        if (!isPatternGridActive(fresh)) {
          if (fresh.status === 'completed') {
            toast.success(`Pattern Grid #${fresh.id} completato`)
            void loadCandidates(fresh.id)
          } else if (fresh.status === 'failed') {
            toast.error(`Pattern Grid #${fresh.id} fallito: ${fresh.error?.message ?? ''}`)
          }
        }
      } catch {
        /* polling: errori ignorati */
      }
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [activeRun, loadCandidates])

  const handleStart = async () => {
    setStarting(true)
    try {
      const run = await startPatternGridRun(marketKey, DEFAULT_RUN_IDS, competition.trim() || null)
      setActiveRun(run)
      setCandidates([])
      toast.success(`Pattern Grid #${run.id} avviato su ${marketKey}${competition ? ' / ' + competition : ' (globale)'}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Avvio Pattern Grid fallito')
    } finally {
      setStarting(false)
    }
  }

  const handleCancel = async () => {
    if (!activeRun) return
    try {
      const fresh = await cancelPatternGridRun(activeRun.id)
      setActiveRun(fresh)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Annullamento fallito')
    }
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="lab-card p-4">
        <h2 className="text-lg font-semibold">Pattern Grid — ricerca esaustiva sequenziale</h2>
        <p className="mt-1 text-sm" style={{ color: 'var(--lab-muted)' }}>
          Ricerca alla cieca (non parte dai pattern già noti in League Pattern Analysis) su tutte le
          combinazioni di 1-2 filtri per mercato, eseguita in sequenza sui 4 pacchetti stagionali
          2021/22→2024/25. Ogni candidato porta lo storico completo: nato a quale stadio, confermato o
          decaduto negli stadi successivi.
        </p>

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Mercato
            <select
              className="lab-input"
              value={marketKey}
              onChange={(e) => setMarketKey(e.target.value)}
            >
              {PATTERN_GRID_MARKET_KEYS.map((mk) => (
                <option key={mk} value={mk}>
                  {mk}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Campionato (vuoto = globale)
            <input
              className="lab-input"
              placeholder="es. Serie A"
              value={competition}
              onChange={(e) => setCompetition(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="lab-btn"
            disabled={starting || (activeRun ? isPatternGridActive(activeRun) : false)}
            onClick={() => void handleStart()}
          >
            {starting ? 'Avvio…' : 'Avvia ricerca'}
          </button>
          {activeRun && isPatternGridActive(activeRun) && (
            <button type="button" className="lab-btn-ghost" onClick={() => void handleCancel()}>
              Annulla
            </button>
          )}
        </div>

        {activeRun && (
          <div className="mt-3 text-sm" style={{ color: 'var(--lab-muted)' }}>
            Run #{activeRun.id} — {activeRun.market_key}
            {activeRun.competition ? ` / ${activeRun.competition}` : ' (globale)'} — stato:{' '}
            <strong>{activeRun.status}</strong>
            {isPatternGridActive(activeRun) && (
              <> — stadio {activeRun.stages_processed}/{activeRun.stages_total || '?'}</>
            )}
            {activeRun.summary?.verdict_counts && (
              <span className="ml-2">
                {Object.entries(activeRun.summary.verdict_counts)
                  .map(([k, v]) => `${verdictLabel(k as PatternGridCandidate['final_verdict'])}: ${v}`)
                  .join(' · ')}
              </span>
            )}
          </div>
        )}
      </div>

      {loadingCandidates && <div style={{ color: 'var(--lab-muted)' }}>Caricamento candidati…</div>}

      {candidates.length > 0 && (
        <div className="lab-card p-0">
          <div className="lab-table-wrap">
            <table className="lab-table w-full min-w-[900px]">
              <thead>
                <tr>
                  <th className="text-left">Pattern</th>
                  <th className="text-left">Nato a</th>
                  {STAGE_SEASON_LABELS.map((label, i) => (
                    <th key={label} className="text-left">
                      Stadio {i + 1} ({label})
                    </th>
                  ))}
                  <th className="text-left">Verdetto</th>
                </tr>
              </thead>
              <tbody>
                {candidates
                  .slice()
                  .sort((a, b) => a.born_stage - b.born_stage)
                  .map((c) => (
                    <tr key={c.id}>
                      <td className="max-w-[320px] text-xs">
                        {c.filters_text}
                        {c.refined_from_text && (
                          <div style={{ color: 'var(--lab-muted)' }}>
                            raffinamento di: {c.refined_from_text}
                          </div>
                        )}
                      </td>
                      <td>Stadio {c.born_stage}</td>
                      {[1, 2, 3, 4].map((stage) => (
                        <td key={stage}>
                          <StageCell result={c.per_stage[String(stage)]} />
                        </td>
                      ))}
                      <td>
                        <span className={`${verdictBadgeClass(c.final_verdict)} rounded px-2 py-1 text-xs`}>
                          {verdictLabel(c.final_verdict)}
                        </span>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loadingCandidates && candidates.length === 0 && activeRun?.status === 'completed' && (
        <div style={{ color: 'var(--lab-muted)' }}>Nessun candidato trovato per questa combinazione.</div>
      )}
    </div>
  )
}
