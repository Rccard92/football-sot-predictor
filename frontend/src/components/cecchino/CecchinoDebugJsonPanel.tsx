import { useMemo } from 'react'
import type { CecchinoFixtureDetailResponse } from '../../lib/cecchinoApi'

type Props = {
  detail: CecchinoFixtureDetailResponse
}

export function CecchinoDebugJsonPanel({ detail }: Props) {
  const json = useMemo(() => {
    try {
      return JSON.stringify(detail, null, 2)
    } catch {
      return '{"error":"serializzazione JSON non riuscita"}'
    }
  }, [detail])

  return (
    <details className="rounded-xl border border-slate-200 bg-slate-50">
      <summary className="cursor-pointer px-4 py-2 text-sm font-medium text-slate-700">
        Debug tecnico
      </summary>
      <pre className="max-h-96 overflow-auto border-t border-slate-200 p-4 text-[11px] text-slate-800">
        {json}
      </pre>
    </details>
  )
}
