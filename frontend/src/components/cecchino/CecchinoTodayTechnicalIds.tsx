import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'

type Props = {
  detail: CecchinoTodayDetailResponse
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export function CecchinoTodayTechnicalIds({ detail }: Props) {
  const [copied, setCopied] = useState(false)
  const ids = detail.fixture_ids
  const todayId = ids?.today_fixture_id ?? detail.today_fixture_id ?? detail.id
  const localId = ids?.local_fixture_id ?? detail.local_fixture_id
  const providerId = ids?.provider_fixture_id ?? detail.provider_fixture_id

  const handleCopyProvider = async () => {
    if (providerId == null) return
    const ok = await copyText(String(providerId))
    if (ok) {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <details className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2 text-xs text-slate-600">
      <summary className="cursor-pointer font-medium text-slate-700">ID tecnici</summary>
      <dl className="mt-2 space-y-1">
        <div className="flex flex-wrap gap-x-2">
          <dt className="font-medium">Today:</dt>
          <dd className="tabular-nums">{todayId ?? '—'}</dd>
        </div>
        <div className="flex flex-wrap gap-x-2">
          <dt className="font-medium">Local:</dt>
          <dd className="tabular-nums">{localId ?? '—'}</dd>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <dt className="font-medium">API-Football:</dt>
          <dd className="tabular-nums">{providerId ?? '—'}</dd>
          {providerId != null ? (
            <>
              <button
                type="button"
                onClick={() => void handleCopyProvider()}
                className="rounded border border-slate-300 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700 hover:bg-slate-100"
              >
                {copied ? 'Copiato' : 'Copia'}
              </button>
              <Link
                to={`/bookmakers?provider_fixture_id=${providerId}`}
                className="rounded border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-800 hover:bg-indigo-100"
              >
                Apri debug bookmakers
              </Link>
            </>
          ) : null}
        </div>
      </dl>
    </details>
  )
}
