import { useCallback, useEffect, useState } from 'react'
import {
  getPredictiveAiInsights,
  getPredictiveSimulatorConfig,
  postPredictiveAiInsights,
  type PredictiveAiInsights,
} from '../../lib/api'

type Props = {
  runId: number | null
}

export function PredictiveAiInsightsPanel({ runId }: Props) {
  const [configured, setConfigured] = useState(false)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<PredictiveAiInsights | null>(null)

  useEffect(() => {
    void getPredictiveSimulatorConfig().then((c) => setConfigured(c.openai_configured))
  }, [])

  const loadLatest = useCallback(async () => {
    if (runId == null) return
    setLoading(true)
    setError(null)
    try {
      const res = await getPredictiveAiInsights(runId)
      setData(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    void loadLatest()
  }, [loadLatest])

  const generate = async () => {
    if (runId == null) return
    setGenerating(true)
    setError(null)
    try {
      const res = await postPredictiveAiInsights(runId)
      setData(res)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('503') || msg.includes('OPENAI_NOT_CONFIGURED')) {
        setError('OpenAI non configurato. Imposta OPENAI_API_KEY nel backend.')
      } else {
        setError(msg)
      }
    } finally {
      setGenerating(false)
    }
  }

  if (runId == null) {
    return (
      <p className="text-sm text-slate-600">
        Apri un&apos;analisi salvata per generare o consultare l&apos;analisi AI diagnostica.
      </p>
    )
  }

  const output = data?.output

  return (
    <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold text-slate-900">Analisi AI (solo diagnostica)</h2>
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${configured ? 'bg-emerald-100 text-emerald-900' : 'bg-slate-100 text-slate-700'}`}
        >
          OpenAI: {configured ? 'configurato' : 'non configurato'}
        </span>
        <button
          type="button"
          disabled={!configured || generating}
          className="rounded border border-violet-700 px-3 py-1 text-xs text-violet-800 hover:bg-violet-50 disabled:opacity-50"
          onClick={() => void generate()}
        >
          {generating ? 'Generazione…' : 'Genera analisi AI'}
        </button>
      </div>

      <p className="text-xs text-slate-600">
        L&apos;AI analizza errori e pattern post-match. Non predice SOT futuri e non modifica i pesi del
        modello.
      </p>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {loading ? <p className="text-xs text-slate-600">Caricamento…</p> : null}

      {output ? (
        <div className="space-y-3 text-xs text-slate-800">
          {output.headline ? (
            <p className="text-sm font-semibold text-slate-900">{String(output.headline)}</p>
          ) : null}
          {Array.isArray(output.structural_issues) && output.structural_issues.length > 0 ? (
            <div>
              <h3 className="font-medium">Problemi strutturali</h3>
              <ul className="mt-1 list-disc pl-4">
                {(output.structural_issues as unknown[]).map((item, i) => (
                  <li key={i}>{typeof item === 'string' ? item : JSON.stringify(item)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {Array.isArray(output.recommended_experiments) && output.recommended_experiments.length > 0 ? (
            <div>
              <h3 className="font-medium">Esperimenti consigliati</h3>
              <ul className="mt-1 list-disc pl-4">
                {(output.recommended_experiments as unknown[]).map((item, i) => (
                  <li key={i}>{typeof item === 'string' ? item : JSON.stringify(item)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <pre className="overflow-x-auto rounded bg-slate-50 p-3 text-[10px]">
            {JSON.stringify(output, null, 2)}
          </pre>
        </div>
      ) : (
        !loading && <p className="text-xs text-slate-600">Nessuna analisi AI salvata per questa run.</p>
      )}
    </section>
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
