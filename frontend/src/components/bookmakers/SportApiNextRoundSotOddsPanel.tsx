import { useState } from 'react'
import {
  postSportApiNextRoundSot,
  SPORTAPI_DEFAULT_PROVIDER_SLUG,
  type SportApiNextRoundSotResponse,
} from '../../lib/api'

function formatKickoff(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('it-IT', {
      weekday: 'short',
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatOdd(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

function rowStatusLabel(status: string): string {
  switch (status) {
    case 'ok':
      return 'OK'
    case 'no_over_under':
      return 'Senza O/U'
    case 'market_not_found':
      return 'Mercato assente'
    case 'api_error':
      return 'Errore API'
    case 'no_mapping':
      return 'No mapping evento'
    default:
      return status
  }
}

export function SportApiNextRoundSotOddsPanel() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SportApiNextRoundSotResponse | null>(null)

  const run = async () => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const out = await postSportApiNextRoundSot(
        { provider_slug: SPORTAPI_DEFAULT_PROVIDER_SLUG, market_key: 'match_total_sot' },
        { timeoutMs: 300_000 },
      )
      setResult(out)
      if (out.message && (out.rows?.length ?? 0) === 0) {
        setError(out.message)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-2xl border border-amber-200/80 bg-amber-50/30 p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-amber-950">Test recupero SOT prossimo turno</h2>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
        Per ogni partita del turno corrente cerca il mercato mappato come{' '}
        <span className="font-medium">match_total_sot</span> e mostra Over/Under. Configura prima i mapping
        nella sezione Discovery.
      </p>

      <button
        type="button"
        disabled={busy}
        onClick={() => void run()}
        className="mt-3 rounded-md border border-amber-500 bg-white px-3 py-1.5 text-[11px] font-medium text-amber-900 hover:bg-amber-100 disabled:opacity-50"
      >
        {busy ? 'Recupero in corso…' : 'Test recupero SOT prossimo turno'}
      </button>

      {error ? (
        <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-800">
          {error}
        </p>
      ) : null}

      {result ? (
        <div className="mt-4 space-y-2">
          <p className="text-[11px] text-slate-700">
            Mapping attivi: <span className="font-medium">{result.mappings_count}</span> · Partite:{' '}
            <span className="font-medium">{result.total_fixtures}</span>
          </p>
          {(result.rows?.length ?? 0) > 0 ? (
            <div className="overflow-x-auto rounded border border-slate-200 bg-white">
              <table className="w-full min-w-[640px] border-collapse text-[10px]">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-left text-slate-600">
                    <th className="px-2 py-1.5">Data/Ora</th>
                    <th className="px-2 py-1.5">Match</th>
                    <th className="px-2 py-1.5">Mercato</th>
                    <th className="px-2 py-1.5">Linea</th>
                    <th className="px-2 py-1.5">Over</th>
                    <th className="px-2 py-1.5">Under</th>
                    <th className="px-2 py-1.5">Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((r) => (
                    <tr key={r.fixture_id} className="border-b border-slate-100">
                      <td className="px-2 py-1.5 whitespace-nowrap">{formatKickoff(r.kickoff_at)}</td>
                      <td className="px-2 py-1.5 font-medium text-slate-800">{r.match_label}</td>
                      <td className="px-2 py-1.5">{r.market_name ?? '—'}</td>
                      <td className="px-2 py-1.5">{r.line ?? '—'}</td>
                      <td className="px-2 py-1.5">{formatOdd(r.over_odd)}</td>
                      <td className="px-2 py-1.5">{formatOdd(r.under_odd)}</td>
                      <td className="px-2 py-1.5">{rowStatusLabel(r.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
