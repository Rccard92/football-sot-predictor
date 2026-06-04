import { useState } from 'react'
import {
  getPredictiveComponentComparisonReport,
  type ComponentComparisonReport,
} from '../../lib/api'

type Props = {
  runId: number | null
  strategyKey?: string
}

export function PredictiveComponentComparisonExport({ runId, strategyKey }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const download = async (detail: 'summary' | 'full') => {
    if (runId == null) return
    setLoading(true)
    setError(null)
    try {
      const report: ComponentComparisonReport = await getPredictiveComponentComparisonReport(
        runId,
        {
          detail,
          strategy_key: strategyKey || undefined,
        },
      )
      const blob = new Blob([JSON.stringify(report, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `predetto-vs-reale-run-${runId}-${detail}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  if (runId == null) return null

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={loading}
        className="rounded border border-violet-300 bg-violet-50 px-3 py-1 text-xs text-violet-900 hover:bg-violet-100 disabled:opacity-50"
        onClick={() => void download('summary')}
      >
        Scarica Predetto vs Reale JSON (summary)
      </button>
      <button
        type="button"
        disabled={loading}
        className="rounded border border-slate-300 px-3 py-1 text-xs hover:bg-slate-50 disabled:opacity-50"
        onClick={() => void download('full')}
      >
        Export completo
      </button>
      {error ? <span className="text-xs text-rose-700">{error}</span> : null}
    </div>
  )
}
