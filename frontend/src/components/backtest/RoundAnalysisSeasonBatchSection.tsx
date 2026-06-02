import { useEffect, useMemo, useRef, useState } from 'react'
import { Card } from '../ui/Card'
import { postRoundAnalysisAnalyze } from '../../lib/api'

type Props = {
  competitionId: number | null
  seasonYear: number
  seasonLabel: string
  onReloadList: () => void
}

const MODEL_OPTIONS = [
  { id: 'v11', label: 'v1.1', key: 'baseline_v1_1_sot' },
  { id: 'v20', label: 'v2.0', key: 'baseline_v2_0_lineup_impact' },
  { id: 'v21', label: 'v2.1', key: 'baseline_v2_1_weighted_components' },
  { id: 'v30', label: 'v3.0', key: 'baseline_v3_0_sot_value_selector' },
] as const

const DEFAULT_FROM = 4
const DEFAULT_TO = 38
const LS_V30_DEFAULT_APPLIED = 'backtest.seasonBatch.v30DefaultApplied'

type BatchStatus = 'idle' | 'running' | 'done' | 'cancelled'

type LogLine = {
  ts: number
  text: string
}

export function RoundAnalysisSeasonBatchSection({
  competitionId,
  seasonYear,
  seasonLabel,
  onReloadList,
}: Props) {
  const [fromRound, setFromRound] = useState(DEFAULT_FROM)
  const [toRound, setToRound] = useState(DEFAULT_TO)
  const [status, setStatus] = useState<BatchStatus>('idle')
  const [errorCount, setErrorCount] = useState(0)
  const [skippedCount, setSkippedCount] = useState(0)
  const [completedCount, setCompletedCount] = useState(0)
  const [currentRound, setCurrentRound] = useState<number | null>(null)
  const [lastMessage, setLastMessage] = useState<string | null>(null)
  const [logLines, setLogLines] = useState<LogLine[]>([])
  const [logExpanded, setLogExpanded] = useState(false)
  const [selected, setSelected] = useState<Record<string, boolean>>({
    v11: false,
    v20: false,
    v21: false,
    v30: false,
  })
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    try {
      const applied = localStorage.getItem(LS_V30_DEFAULT_APPLIED)
      if (!applied) {
        setSelected({ v11: false, v20: false, v21: false, v30: true })
        localStorage.setItem(LS_V30_DEFAULT_APPLIED, '1')
      }
    } catch {
      // ignore
    }
  }, [])

  const rounds = useMemo(() => {
    const start = Math.max(1, Math.min(50, Number(fromRound) || DEFAULT_FROM))
    const end = Math.max(1, Math.min(50, Number(toRound) || DEFAULT_TO))
    const a = Math.min(start, end)
    const b = Math.max(start, end)
    return Array.from({ length: b - a + 1 }, (_, i) => a + i)
  }, [fromRound, toRound])

  const selectedModels = useMemo(() => {
    return MODEL_OPTIONS.filter((o) => selected[o.id]).map((o) => o.key)
  }, [selected])

  const canRun = competitionId != null && status !== 'running' && selectedModels.length > 0

  const appendLog = (text: string) => {
    const line: LogLine = { ts: Date.now(), text }
    setLogLines((prev) => [...prev, line])
  }

  const resetProgress = () => {
    setErrorCount(0)
    setSkippedCount(0)
    setCompletedCount(0)
    setCurrentRound(null)
    setLastMessage(null)
    setLogLines([])
    setLogExpanded(false)
  }

  const runBatch = async (onlyMissing: boolean) => {
    if (competitionId == null) return
    if (selectedModels.length === 0) return

    resetProgress()
    setStatus('running')
    const ac = new AbortController()
    abortRef.current = ac

    const total = rounds.length
    for (let i = 0; i < rounds.length; i++) {
      if (ac.signal.aborted) {
        setStatus('cancelled')
        setLastMessage('Batch annullata.')
        break
      }
      const rn = rounds[i]
      setCurrentRound(rn)
      setLastMessage(`Analisi giornata ${rn}…`)
      try {
        const res = await postRoundAnalysisAnalyze({
          competition_id: competitionId,
          season_year: seasonYear,
          round_number: rn,
          mode: 'historical_official_xi',
          selected_models: selectedModels,
          merge_mode: 'upsert_selected_models',
          only_missing_models: onlyMissing,
          visible_card_mode: 'latest_only',
        })
        if (res.status === 'skipped') {
          setSkippedCount((n) => n + 1)
          const msg = `Giornata ${rn}: saltata (modelli già presenti)`
          setLastMessage(msg)
          appendLog(msg)
        } else {
          setCompletedCount((n) => n + 1)
          const label = selectedModels.length === 1 && selectedModels[0].includes('v3_0')
            ? 'v3.0'
            : `${selectedModels.length} modelli`
          const msg = `Giornata ${rn}: aggiornata (${label})`
          setLastMessage(msg)
          appendLog(msg)
        }
      } catch (e) {
        setErrorCount((n) => n + 1)
        const msg = `Giornata ${rn}: errore (${e instanceof Error ? e.message : String(e)})`
        setLastMessage(msg)
        appendLog(msg)
        // continua
      } finally {
        // progress update implicito dopo ogni giornata
        const done = i + 1
        if (done === total) {
          setStatus('done')
          abortRef.current = null
          onReloadList()
        }
      }
    }
  }

  const progressPct = useMemo(() => {
    const done = completedCount + skippedCount + errorCount
    const total = rounds.length || 1
    return Math.min(100, Math.round((100 * done) / total))
  }, [completedCount, skippedCount, errorCount, rounds.length])

  const visibleLog = logExpanded ? logLines : logLines.slice(-10)

  return (
    <Card title="Analizza stagione">
      <div className="space-y-4 text-sm text-slate-700">
        <p className="text-sm text-slate-600">
          Analizza o aggiorna più giornate senza duplicare le schede già presenti.
        </p>

        <div className="grid gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className="font-medium text-slate-800">Da giornata</span>
            <input
              type="number"
              min={1}
              max={50}
              className="rounded-lg border border-slate-200 px-3 py-2"
              value={fromRound}
              onChange={(e) => setFromRound(Number(e.target.value))}
              disabled={status === 'running'}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium text-slate-800">A giornata</span>
            <input
              type="number"
              min={1}
              max={50}
              className="rounded-lg border border-slate-200 px-3 py-2"
              value={toRound}
              onChange={(e) => setToRound(Number(e.target.value))}
              disabled={status === 'running'}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium text-slate-800">Stagione</span>
            <input
              type="text"
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
              value={seasonLabel}
              readOnly
            />
          </label>
        </div>

        <div className="space-y-2">
          <div className="font-medium text-slate-800">Modelli</div>
          <div className="grid gap-2 sm:grid-cols-4">
            {MODEL_OPTIONS.map((o) => (
              <label key={o.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={!!selected[o.id]}
                  onChange={(e) => setSelected((prev) => ({ ...prev, [o.id]: e.target.checked }))}
                  disabled={status === 'running'}
                />
                <span>{o.label}</span>
              </label>
            ))}
          </div>
          <p className="text-xs text-slate-500">
            Seleziona solo i modelli che vuoi calcolare. I risultati degli altri modelli verranno mantenuti.
          </p>
          <p className="text-xs text-slate-500">
            Se selezioni solo v3.0, il sistema aggiornerà le giornate esistenti aggiungendo solo la v3.0, senza
            ricalcolare v1.1/v2.0/v2.1.
          </p>
          {selectedModels.length === 0 ? (
            <p className="text-xs font-medium text-rose-700">Seleziona almeno un modello.</p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!canRun}
            onClick={() => void runBatch(false)}
            className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50"
          >
            Analizza stagione
          </button>
          <button
            type="button"
            disabled={!canRun}
            onClick={() => void runBatch(true)}
            className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-800 disabled:opacity-50"
          >
            Aggiorna solo modelli mancanti
          </button>
          {status === 'running' ? (
            <button
              type="button"
              onClick={() => abortRef.current?.abort()}
              className="rounded-lg border border-rose-300 px-4 py-2 font-medium text-rose-700"
            >
              Annulla
            </button>
          ) : null}
        </div>

        {status === 'running' || status === 'done' || status === 'cancelled' ? (
          <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center gap-3">
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full bg-slate-900"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <div className="w-12 text-right text-xs tabular-nums">{progressPct}%</div>
            </div>

            <div className="text-xs text-slate-700">
              <div>
                Analisi giornata {currentRound ?? '—'} di {rounds[rounds.length - 1] ?? '—'}
              </div>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                <span>Completate {completedCount} / {rounds.length}</span>
                <span>Saltate {skippedCount}</span>
                <span>Errori: {errorCount}</span>
              </div>
              {lastMessage ? <div className="mt-1">{lastMessage}</div> : null}
              <div className="mt-2 text-slate-500">
                L’analisi viene eseguita giornata per giornata per evitare timeout.
              </div>
            </div>
          </div>
        ) : null}

        {logLines.length > 0 ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="font-medium text-slate-800">Log batch</div>
              {logLines.length > 10 ? (
                <button
                  type="button"
                  className="text-xs text-slate-600 underline"
                  onClick={() => setLogExpanded((v) => !v)}
                >
                  {logExpanded ? 'Compatta' : 'Espandi'}
                </button>
              ) : null}
            </div>
            <div className="max-h-48 overflow-auto rounded-lg border border-slate-200 bg-white p-2 text-xs text-slate-700">
              {visibleLog.map((l) => (
                <div key={l.ts} className="whitespace-pre-wrap">
                  {l.text}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </Card>
  )
}

