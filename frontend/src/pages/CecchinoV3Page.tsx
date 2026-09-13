import { useCallback, useEffect, useState } from 'react'
import { PatternInsightsShell, Section } from '../components/pattern-insights/PatternInsightsShell'
import {
  AccuracyBlock,
  CalibrationBlock,
  CompetitionBlock,
  ExamBlock,
  OrchestratorBlock,
  RunDetailsBlock,
} from '../components/cecchino-v3/V3Blocks'
import {
  cancelV3Run,
  getLatestV3Runs,
  getV3Run,
  isV3RunActive,
  listV3Runs,
  startV3Run,
  type V3Run,
  type V3RunListItem,
} from '../lib/cecchinoV3Api'

const PHASE_TITLES: Record<number, string> = {
  1: 'Fase 1 · Specialista Forza',
  2: 'Fase 2 · Forza + Gioco + orchestratore',
}

const POLL_MS = 10000

export function CecchinoV3Page() {
  const [latest, setLatest] = useState<V3Run | null>(null)
  const [completed, setCompleted] = useState<V3Run | null>(null)
  const [runs, setRuns] = useState<V3RunListItem[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [selected, setSelected] = useState<V3Run | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [res, list] = await Promise.all([getLatestV3Runs(), listV3Runs()])
      setLatest(res.latest)
      setCompleted(res.completed)
      setRuns(list.items)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento V3')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (selectedId == null) {
      setSelected(null)
      return
    }
    let alive = true
    getV3Run(selectedId)
      .then((r) => alive && setSelected(r))
      .catch(() => alive && setSelected(null))
    return () => {
      alive = false
    }
  }, [selectedId])

  const active = isV3RunActive(latest)
  useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(t)
  }, [active, load])

  const start = async () => {
    setBusy(true)
    try {
      await startV3Run(2)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Avvio non riuscito')
    } finally {
      setBusy(false)
    }
  }

  const cancel = async () => {
    if (!latest) return
    setBusy(true)
    try {
      await cancelV3Run(latest.id)
      await load()
    } finally {
      setBusy(false)
    }
  }

  const shown = selected ?? completed
  const evaluation = shown?.summary?.evaluation
  const config = (shown ?? latest)?.config
  const shownPhase = shown?.phase ?? 1

  return (
    <PatternInsightsShell>
      <header className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight">Cecchino V3</h1>
          <span className="pi-chip">{PHASE_TITLES[shownPhase] ?? `Fase ${shownPhase}`}</span>
          {config ? (
            <>
              <span className="pi-chip">Rodaggio {config.warmup_season}</span>
              <span className="pi-chip">Giudizio {config.judge_seasons.join(' · ')}</span>
              <span className="pi-chip">{config.lockbox_season} sotto chiave</span>
              <span className="pi-chip">Minimo {config.min_matches_played} partite giocate</span>
              <span className="pi-chip">Finale = ultime {config.final_phase_matches} giornate</span>
            </>
          ) : null}
        </div>
        <p className="mt-2 max-w-4xl text-xs leading-relaxed" style={{ color: 'var(--pi-muted)' }}>
          Motore nuovo, in parallelo alla V2 che resta invariata. Stima la forza di attacco e difesa di ogni squadra
          dai gol, corretta per gli avversari affrontati, per il vantaggio casa di ogni campionato e con continuita&apos;
          tra stagioni e tra divisioni (promosse e retrocesse). Ogni partita e&apos; prevista usando solo le partite
          dei giorni precedenti. Da un&apos;unica distribuzione dei risultati escono tutti i 17 mercati. Dalla Fase 2
          lo specialista Gioco stima quanti tiri e tiri in porta produce e concede ogni squadra e li traduce in gol
          attesi; l&apos;orchestratore combina le opinioni con pesi imparati sulla stagione precedente.
        </p>
        {runs.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
              Calcolo mostrato:
            </span>
            {runs.map((r) => {
              const active = (selectedId ?? completed?.id) === r.id
              return (
                <button
                  key={r.id}
                  type="button"
                  className="pi-btn"
                  style={active ? { borderColor: 'var(--pi-accent)', color: 'var(--pi-accent)' } : undefined}
                  onClick={() => setSelectedId(r.id)}
                >
                  #{r.id} · Fase {r.phase}
                  {r.exam_passed == null ? '' : r.exam_passed ? ' · ✓' : ' · ✗'}
                </button>
              )
            })}
          </div>
        )}
      </header>

      {error && (
        <div
          className="mb-4 rounded-xl border px-3 py-2 text-xs"
          style={{ borderColor: 'rgba(248,113,113,0.4)', background: 'rgba(248,113,113,0.08)', color: '#fca5a5' }}
        >
          {error}
        </div>
      )}

      <div className="space-y-4">
        <Section title="Calcolo" note={latest ? `Ultimo calcolo #${latest.id}` : 'Nessun calcolo ancora eseguito'}>
          {active && latest ? (
            <div>
              <div className="flex items-center justify-between text-xs">
                <span>{latest.current_step ?? 'In attesa di avvio'}</span>
                <span className="tabular-nums">{(latest.progress_pct ?? 0).toFixed(1)}%</span>
              </div>
              <div className="mt-2 h-2 w-full rounded-full" style={{ background: '#1a2438' }}>
                <div
                  className="h-2 rounded-full"
                  style={{ width: `${latest.progress_pct ?? 0}%`, background: 'var(--pi-accent)' }}
                />
              </div>
              <button type="button" className="pi-btn mt-3" disabled={busy} onClick={() => void cancel()}>
                Annulla calcolo
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className="pi-btn" disabled={busy} onClick={() => void start()}>
                Avvia calcolo Fase 2
              </button>
              {latest?.status === 'failed' && (
                <span className="text-xs" style={{ color: '#fca5a5' }}>
                  Ultimo calcolo fallito: {latest.error?.message ?? 'errore sconosciuto'}
                </span>
              )}
              {latest?.status === 'cancelled' && (
                <span className="text-xs" style={{ color: 'var(--pi-muted)' }}>
                  Ultimo calcolo annullato
                </span>
              )}
            </div>
          )}
        </Section>

        {evaluation && shown ? (
          <>
            <ExamBlock evaluation={evaluation} phase={shownPhase} />
            <AccuracyBlock evaluation={evaluation} />
            <OrchestratorBlock run={shown} />
            <CalibrationBlock evaluation={evaluation} />
            <CompetitionBlock evaluation={evaluation} />
            <RunDetailsBlock run={shown} />
          </>
        ) : null}
      </div>
    </PatternInsightsShell>
  )
}
