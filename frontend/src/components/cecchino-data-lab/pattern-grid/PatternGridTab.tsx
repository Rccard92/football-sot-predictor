import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  PATTERN_GRID_MARKET_KEYS,
  cancelPatternGridRun,
  formatRoiPct,
  getPatternGridLeaderboard,
  getPatternGridRun,
  isPatternGridActive,
  startPatternGridRun,
  verdictBadgeClass,
  verdictLabel,
  type PatternGridCandidate,
  type PatternGridLeaderboard,
  type PatternGridRun,
  type PatternGridVerdict,
} from '../../../lib/cecchinoPatternGridApi'
import { roiColor } from '../overview/overviewTheme'

const POLL_MS = 3000
const DEFAULT_RUN_IDS = [17, 19, 20, 21]
const STAGE_SEASON_LABELS = ['2021/22', '2022/23', '2023/24', '2024/25']

const ALL_VERDICTS: PatternGridVerdict[] = [
  'stable',
  'confirmed_once',
  'weakening',
  'decaying',
  'pending_first_oos',
  'rejected',
]

function StageCell({ result }: { result?: { status: string; roi_pct: number | null; n: number } }) {
  if (!result) {
    return <span style={{ color: 'var(--lab-muted)' }}>— non nato</span>
  }
  if (result.status === 'insufficient_sample') {
    return (
      <span style={{ color: 'var(--lab-muted)' }} title={`N=${result.n}, campione insufficiente`}>
        camp. insuff. (N={result.n})
      </span>
    )
  }
  const ok = result.status === 'confirmed'
  return (
    <span className="whitespace-nowrap text-xs" title={`N=${result.n}`}>
      <span className={`lab-badge-${ok ? 'ok' : 'err'} rounded px-1.5 py-0.5`}>{ok ? '✓' : '✗'}</span>{' '}
      <span style={{ color: roiColor(result.roi_pct ?? 0) }}>{formatRoiPct(result.roi_pct)}</span>
    </span>
  )
}

function CandidateRow({ c }: { c: PatternGridCandidate }) {
  return (
    <tr>
      <td className="whitespace-nowrap text-xs font-semibold">{c.market_label}</td>
      <td
        className="min-w-[260px] max-w-[380px] text-xs"
        style={{ whiteSpace: 'normal', wordBreak: 'break-word' }}
      >
        {c.filters_text_human}
        {c.competition && (
          <div style={{ color: 'var(--lab-cyan)' }}>· {c.competition}</div>
        )}
      </td>
      <td className="whitespace-nowrap text-xs">Stadio {c.born_stage}</td>
      {[1, 2, 3, 4].map((stage) => (
        <td key={stage} className="whitespace-nowrap">
          <StageCell result={c.per_stage[String(stage)]} />
        </td>
      ))}
      <td className="whitespace-nowrap text-xs">
        <div>N {c.total_n ?? '—'}</div>
        <div style={{ color: roiColor(c.total_roi_pct ?? 0) }} className="font-semibold">
          ROI {formatRoiPct(c.total_roi_pct)}
        </div>
      </td>
      <td className="whitespace-nowrap">
        <span className={`${verdictBadgeClass(c.final_verdict)} rounded px-2 py-1 text-xs`}>
          {verdictLabel(c.final_verdict)}
        </span>
      </td>
    </tr>
  )
}

export function PatternGridTab() {
  const [data, setData] = useState<PatternGridLeaderboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  // Sezione avanzata: avvio manuale di un singolo mercato/campionato (facoltativo).
  const [marketKey, setMarketKey] = useState<string>('DRAW')
  const [competition, setCompetition] = useState('')
  const [activeRun, setActiveRun] = useState<PatternGridRun | null>(null)
  const [starting, setStarting] = useState(false)

  const [selectedVerdicts, setSelectedVerdicts] = useState<Set<PatternGridVerdict>>(
    () => new Set(ALL_VERDICTS),
  )

  const toggleVerdict = (v: PatternGridVerdict) => {
    setSelectedVerdicts((prev) => {
      const next = new Set(prev)
      if (next.has(v)) {
        next.delete(v)
      } else {
        next.add(v)
      }
      return next
    })
  }

  const loadLeaderboard = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = await getPatternGridLeaderboard()
      setData(payload)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento classifica Pattern Grid')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadLeaderboard()
  }, [loadLeaderboard])

  useEffect(() => {
    if (!activeRun || !isPatternGridActive(activeRun)) return
    const id = window.setInterval(async () => {
      try {
        const fresh = await getPatternGridRun(activeRun.id)
        setActiveRun(fresh)
        if (!isPatternGridActive(fresh)) {
          if (fresh.status === 'completed') {
            toast.success(`Pattern Grid #${fresh.id} completato — aggiorno la classifica`)
            void loadLeaderboard()
          } else if (fresh.status === 'failed') {
            toast.error(`Pattern Grid #${fresh.id} fallito: ${fresh.error?.message ?? ''}`)
          }
        }
      } catch {
        /* polling: errori ignorati */
      }
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [activeRun, loadLeaderboard])

  const handleStart = async () => {
    setStarting(true)
    try {
      const run = await startPatternGridRun(marketKey, DEFAULT_RUN_IDS, competition.trim() || null)
      setActiveRun(run)
      toast.success(`Analisi avviata su ${marketKey}${competition ? ' / ' + competition : ' (globale)'}`)
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

  const candidates = data?.candidates ?? []
  const marketsCovered = data ? Object.keys(data.runs).length : 0
  const verdictCounts = candidates.reduce<Record<string, number>>((acc, c) => {
    acc[c.final_verdict] = (acc[c.final_verdict] ?? 0) + 1
    return acc
  }, {})
  const filteredCandidates = candidates.filter((c) => selectedVerdicts.has(c.final_verdict))

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="lab-card p-4">
        <h2 className="text-lg font-semibold">Pattern Grid — pattern profittevoli su 4 anni, tutti i mercati</h2>
        <p className="mt-1 text-sm" style={{ color: 'var(--lab-muted)' }}>
          Ricerca cieca (non parte dai pattern già noti in League Pattern Analysis): prova sistematicamente
          combinazioni di 1-3 caratteristiche della partita, mercato per mercato, in sequenza sulle 4 stagioni
          2021/22→2024/25. Qui sotto solo i pattern con <strong>profitto totale positivo sui 4 anni combinati</strong>,
          di tutti i mercati insieme — non filtrati per un singolo segno.
        </p>
        <p className="mt-2 text-xs" style={{ color: 'var(--lab-muted)' }}>
          <strong>Come leggere le colonne Stadio 1-4</strong>: ogni pattern nasce in uno stadio (una stagione, o il
          cumulato fino a quel punto) e viene ri-testato sulle stagioni successive mai viste prima — ✓ verde
          significa che in quell'anno, da solo, il pattern è stato profittevole; ✗ rosso che non lo è stato. Un
          pattern "— non nato" in uno stadio semplicemente non era ancora stato scoperto a quel punto. Se vedi un
          pattern con dati solo nell'ultimo stadio, non è sospetto: significa che serviva tutto il campione di 4
          anni insieme perché quella combinazione raggiungesse una numerosità sufficiente per essere considerata —
          va quindi ancora verificato sulla prima stagione futura disponibile (2025/26) prima di fidarsene.
        </p>
        {data && (
          <p className="mt-2 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Mercati coperti: {marketsCovered}/{PATTERN_GRID_MARKET_KEYS.length} · Pattern a profitto positivo:{' '}
            {candidates.length}
            {filteredCandidates.length !== candidates.length && (
              <> · mostrati con i filtri attuali: {filteredCandidates.length}</>
            )}
          </p>
        )}
      </div>

      {loading && <div style={{ color: 'var(--lab-muted)' }}>Caricamento classifica…</div>}
      {error && <div style={{ color: 'var(--lab-err)' }}>{error}</div>}

      {!loading && !error && candidates.length === 0 && (
        <div style={{ color: 'var(--lab-muted)' }}>
          Nessun risultato ancora disponibile. Avvia l'analisi dalla sezione "Avanzate" qui sotto per i mercati
          che non hai ancora coperto.
        </div>
      )}

      {candidates.length > 0 && (
        <div className="lab-card flex flex-wrap items-center gap-2 p-4">
          <span className="text-xs font-semibold" style={{ color: 'var(--lab-muted)' }}>
            Filtra per verdetto:
          </span>
          {ALL_VERDICTS.map((v) => {
            const active = selectedVerdicts.has(v)
            const count = verdictCounts[v] ?? 0
            return (
              <button
                key={v}
                type="button"
                onClick={() => toggleVerdict(v)}
                title={active ? 'Clicca per nascondere questo verdetto' : 'Clicca per mostrare questo verdetto'}
                className={`${verdictBadgeClass(v)} rounded px-2 py-1 text-xs`}
                style={{
                  opacity: active ? 1 : 0.3,
                  cursor: 'pointer',
                  border: 'none',
                  filter: active ? 'none' : 'grayscale(60%)',
                }}
              >
                {verdictLabel(v)} ({count})
              </button>
            )
          })}
          <button
            type="button"
            className="lab-btn-ghost text-xs"
            onClick={() => setSelectedVerdicts(new Set(ALL_VERDICTS))}
          >
            Tutti
          </button>
          <button
            type="button"
            className="lab-btn-ghost text-xs"
            onClick={() => setSelectedVerdicts(new Set())}
          >
            Nessuno
          </button>
        </div>
      )}

      {candidates.length > 0 && filteredCandidates.length === 0 && (
        <div style={{ color: 'var(--lab-muted)' }}>
          Nessun pattern corrisponde ai verdetti selezionati. Attiva almeno un verdetto qui sopra.
        </div>
      )}

      {filteredCandidates.length > 0 && (
        <div className="lab-card p-0">
          <div className="lab-table-wrap">
            <table className="lab-table w-full min-w-[1000px] table-fixed">
              <colgroup>
                <col style={{ width: '70px' }} />
                <col style={{ width: '300px' }} />
                <col style={{ width: '80px' }} />
                <col style={{ width: '110px' }} />
                <col style={{ width: '110px' }} />
                <col style={{ width: '110px' }} />
                <col style={{ width: '110px' }} />
                <col style={{ width: '100px' }} />
                <col style={{ width: '150px' }} />
              </colgroup>
              <thead>
                <tr>
                  <th className="text-left">Mercato</th>
                  <th className="text-left">Pattern</th>
                  <th className="text-left">Nato a</th>
                  {STAGE_SEASON_LABELS.map((label, i) => (
                    <th key={label} className="text-left">
                      Stadio {i + 1} ({label})
                    </th>
                  ))}
                  <th className="text-left">Totale 4 anni</th>
                  <th className="text-left">Verdetto</th>
                </tr>
              </thead>
              <tbody>
                {filteredCandidates.map((c) => (
                  <CandidateRow key={c.id} c={c} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="lab-card p-4">
        <button
          type="button"
          className="lab-btn-ghost"
          onClick={() => setAdvancedOpen((v) => !v)}
        >
          {advancedOpen ? '▾' : '▸'} Avanzate — avvia/ri-avvia un'analisi (per mercato o campionato)
        </button>
        {advancedOpen && (
          <div className="mt-4">
            <p className="text-xs" style={{ color: 'var(--lab-muted)' }}>
              Usa questa sezione solo per rilanciare un mercato specifico o restringere a un campionato (pattern
              "league-native"). La classifica sopra si aggiorna da sola quando l'analisi finisce.
            </p>
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
                Mercato
                <select className="lab-input" value={marketKey} onChange={(e) => setMarketKey(e.target.value)}>
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
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
