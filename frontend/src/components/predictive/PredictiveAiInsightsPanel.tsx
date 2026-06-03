import { useCallback, useEffect, useState } from 'react'
import {
  getPredictiveAiInsight,
  getPredictiveSimulatorConfig,
  listPredictiveAiInsights,
  postPredictiveAiInsights,
  type PredictiveAiAnalysisType,
  type PredictiveAiHistoryItem,
  type PredictiveAiOutput,
} from '../../lib/api'
import { ANALYSIS_LABELS, PredictiveAiOutputView } from './PredictiveAiOutputView'

type PendingFixture = {
  fixtureId: number
  strategyKey: string
} | null

type Props = {
  runId: number | null
  pendingFixture?: PendingFixture
  onPendingFixtureConsumed?: () => void
}

const ANALYSIS_BLOCKS: Array<{
  type: PredictiveAiAnalysisType
  title: string
  description: string
}> = [
  {
    type: 'missed_high_non_extreme',
    title: '1. High non estreme sottostimate',
    description:
      'Partite con actual alto (non outlier) che i modelli top-3 hanno predetto troppo basse.',
  },
  {
    type: 'false_high_predictions',
    title: '2. False high prediction',
    description: 'Predizione ≥ 9 SOT ma actual ≤ 7: falsi positivi da analizzare.',
  },
  {
    type: 'top3_model_comparison',
    title: '3. Confronto top 3 modelli',
    description: 'Bias corrected vs dynamic high guard vs chaos game su cluster reali.',
  },
  {
    type: 'single_fixture',
    title: '4. Analisi singola partita',
    description: 'Diagnosi mirata su una fixture (da ID o dalla tab Diagnosi partite).',
  },
]

export function PredictiveAiInsightsPanel({
  runId,
  pendingFixture,
  onPendingFixtureConsumed,
}: Props) {
  const [configured, setConfigured] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [generatingType, setGeneratingType] = useState<PredictiveAiAnalysisType | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<PredictiveAiHistoryItem[]>([])
  const [activeOutput, setActiveOutput] = useState<PredictiveAiOutput | null>(null)
  const [activeMeta, setActiveMeta] = useState<{ analysisType?: string; id?: number }>({})
  const [singleFixtureId, setSingleFixtureId] = useState('')
  const [singleStrategyKey, setSingleStrategyKey] = useState('v31_bias_dynamic_high_guard')

  useEffect(() => {
    void getPredictiveSimulatorConfig().then((c) => setConfigured(c.openai_configured))
  }, [])

  const loadHistory = useCallback(async () => {
    if (runId == null) return
    setLoadingHistory(true)
    try {
      const res = await listPredictiveAiInsights(runId, { limit: 20 })
      setHistory(res.items)
    } catch {
      setHistory([])
    } finally {
      setLoadingHistory(false)
    }
  }, [runId])

  useEffect(() => {
    void loadHistory()
    setActiveOutput(null)
    setActiveMeta({})
  }, [loadHistory])

  const runAnalysis = useCallback(
    async (analysisType: PredictiveAiAnalysisType, opts?: { fixtureId?: number; strategyKey?: string }) => {
      if (runId == null) return
      setGeneratingType(analysisType)
      setError(null)
      try {
        const res = await postPredictiveAiInsights(runId, {
          analysis_type: analysisType,
          fixture_id: opts?.fixtureId,
          strategy_key: opts?.strategyKey,
        })
        setActiveOutput(res.output ?? null)
        setActiveMeta({ analysisType: res.analysis_type, id: res.id })
        void loadHistory()
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        if (msg.includes('503') || msg.includes('OPENAI_NOT_CONFIGURED')) {
          setError('OpenAI non configurato. Imposta OPENAI_API_KEY nel backend.')
        } else {
          setError(msg)
        }
      } finally {
        setGeneratingType(null)
      }
    },
    [runId, loadHistory],
  )

  useEffect(() => {
    if (!pendingFixture || runId == null) return
    setSingleFixtureId(String(pendingFixture.fixtureId))
    setSingleStrategyKey(pendingFixture.strategyKey)
    void runAnalysis('single_fixture', {
      fixtureId: pendingFixture.fixtureId,
      strategyKey: pendingFixture.strategyKey,
    })
    onPendingFixtureConsumed?.()
  }, [pendingFixture, runId, runAnalysis, onPendingFixtureConsumed])

  const openHistoryItem = async (item: PredictiveAiHistoryItem) => {
    if (runId == null || item.id == null) return
    try {
      const detail = await getPredictiveAiInsight(runId, item.id)
      setActiveOutput(detail.output ?? null)
      setActiveMeta({ analysisType: detail.analysis_type, id: detail.id })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  if (runId == null) {
    return (
      <p className="text-sm text-slate-600">
        Esegui o apri un&apos;analisi salvata per usare l&apos;AI diagnostica.
      </p>
    )
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-700">
        <p>
          L&apos;AI non predice i SOT e non modifica i pesi. Analizza una run già salvata e aiuta a
          interpretare errori, pattern e possibili esperimenti.
        </p>
        <div className="mt-3 rounded-lg border border-blue-200 bg-blue-50/50 p-3">
          <h3 className="font-semibold text-blue-950">Quando usare l&apos;AI?</h3>
          <p className="mt-1">
            Usala dopo aver eseguito una simulazione salvata. L&apos;AI serve per interpretare errori e
            suggerire esperimenti, non per predire direttamente i SOT.
          </p>
        </div>
        <span
          className={`mt-3 inline-block rounded-full px-2 py-0.5 text-xs ${configured ? 'bg-emerald-100 text-emerald-900' : 'bg-slate-100 text-slate-700'}`}
        >
          OpenAI: {configured ? 'configurato' : 'non configurato'}
        </span>
      </section>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        {ANALYSIS_BLOCKS.map((block) => (
          <section key={block.type} className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">{block.title}</h2>
            <p className="mt-1 text-xs text-slate-600">{block.description}</p>
            {block.type === 'single_fixture' ? (
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <input
                  type="number"
                  placeholder="fixture_id"
                  className="w-28 rounded border border-slate-300 px-2 py-1"
                  value={singleFixtureId}
                  onChange={(e) => setSingleFixtureId(e.target.value)}
                />
                <input
                  placeholder="strategy_key"
                  className="min-w-[180px] flex-1 rounded border border-slate-300 px-2 py-1"
                  value={singleStrategyKey}
                  onChange={(e) => setSingleStrategyKey(e.target.value)}
                />
              </div>
            ) : null}
            <button
              type="button"
              disabled={!configured || generatingType != null}
              className="mt-3 rounded border border-violet-700 px-3 py-1 text-xs text-violet-800 hover:bg-violet-50 disabled:opacity-50"
              onClick={() => {
                if (block.type === 'single_fixture') {
                  const fid = parseInt(singleFixtureId, 10)
                  if (!fid) {
                    setError('Inserisci un fixture_id valido.')
                    return
                  }
                  void runAnalysis('single_fixture', {
                    fixtureId: fid,
                    strategyKey: singleStrategyKey || undefined,
                  })
                } else {
                  void runAnalysis(block.type)
                }
              }}
            >
              {generatingType === block.type ? 'Analisi in corso…' : 'Analizza'}
            </button>
          </section>
        ))}
      </div>

      {activeOutput ? (
        <section className="rounded-lg border border-violet-200 bg-white p-4">
          <PredictiveAiOutputView output={activeOutput} analysisType={activeMeta.analysisType} />
        </section>
      ) : null}

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-900">Ultime analisi AI salvate</h2>
        {loadingHistory ? <p className="mt-2 text-xs text-slate-600">Caricamento…</p> : null}
        {history.length === 0 && !loadingHistory ? (
          <p className="mt-2 text-xs text-slate-600">Nessuna analisi AI salvata per questa run.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-700">
                <tr>
                  <th className="px-2 py-2">Data</th>
                  <th className="px-2 py-2">Tipo</th>
                  <th className="px-2 py-2">Fixture</th>
                  <th className="px-2 py-2">Verdetto</th>
                  <th className="px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {history.map((item) => (
                  <tr key={item.id} className="border-t border-slate-100">
                    <td className="px-2 py-2">
                      {item.created_at ? new Date(item.created_at).toLocaleString('it-IT') : '—'}
                    </td>
                    <td className="px-2 py-2">
                      {ANALYSIS_LABELS[item.analysis_type as PredictiveAiAnalysisType] ??
                        item.analysis_type}
                    </td>
                    <td className="px-2 py-2">{item.fixture_id ?? '—'}</td>
                    <td className="max-w-xs truncate px-2 py-2">{item.short_verdict ?? '—'}</td>
                    <td className="px-2 py-2">
                      <button
                        type="button"
                        className="text-violet-700 underline"
                        onClick={() => void openHistoryItem(item)}
                      >
                        Apri
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

export function PredictiveBettingPhaseNotice() {
  return (
    <p className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 text-xs text-amber-950">
      La fase bet/no bet e valore quota sarà costruita dopo la stabilizzazione diagnostica del modello.
    </p>
  )
}

type AuditProps = {
  audit: Record<string, unknown> | null | undefined
}

export function PredictiveLabAuditPanel({ audit }: AuditProps) {
  const entries = audit ? Object.entries(audit) : []
  const ok = entries.length > 0 && entries.every(([, v]) => v === true)
  return (
    <section className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-4 text-xs">
      <div className="flex items-center gap-2">
        <span
          className={`rounded-full px-2 py-0.5 font-medium ${ok ? 'bg-emerald-200 text-emerald-900' : 'bg-rose-200 text-rose-900'}`}
        >
          Audit laboratorio: {ok ? 'OK' : 'Verifica'}
        </span>
      </div>
      <ul className="mt-3 space-y-1 text-slate-800">
        {entries.map(([k, v]) => (
          <li key={k}>
            {k}: {String(v)}
          </li>
        ))}
      </ul>
      <PredictiveBettingPhaseNotice />
    </section>
  )
}
