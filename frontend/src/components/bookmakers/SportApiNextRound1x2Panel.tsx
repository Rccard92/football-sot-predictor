import { useState } from 'react'
import {
  postSportApiNextRound1x2,
  postSportApiOddsTestEvent,
  SPORTAPI_DEFAULT_PROVIDER_SLUG,
  type SportApiNextRound1x2Response,
  type SportApiOddsTestEventResponse,
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
    case 'incomplete_1x2':
      return '1X2 incompleto'
    case 'no_1x2':
      return 'Senza 1X2'
    case 'api_error':
      return 'Errore API'
    case 'no_mapping':
      return 'No mapping'
    default:
      return status
  }
}

export function SportApiNextRound1x2Panel() {
  const [batchBusy, setBatchBusy] = useState(false)
  const [testBusy, setTestBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [batchResult, setBatchResult] = useState<SportApiNextRound1x2Response | null>(null)
  const [testResult, setTestResult] = useState<SportApiOddsTestEventResponse | null>(null)
  const [eventId, setEventId] = useState('13980080')
  const [rawFtOpen, setRawFtOpen] = useState(false)

  const runBatch = async () => {
    setBatchBusy(true)
    setError(null)
    setBatchResult(null)
    try {
      const out = await postSportApiNextRound1x2(
        { provider_slug: SPORTAPI_DEFAULT_PROVIDER_SLUG },
        { timeoutMs: 300_000 },
      )
      setBatchResult(out)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBatchBusy(false)
    }
  }

  const runTest = async () => {
    const eid = Number(eventId.trim())
    if (!eid) {
      setError('Inserisci un SportAPI event_id valido.')
      return
    }
    setTestBusy(true)
    setError(null)
    setTestResult(null)
    setRawFtOpen(false)
    try {
      const out = await postSportApiOddsTestEvent(
        {
          sportapi_event_id: eid,
          provider_slug: SPORTAPI_DEFAULT_PROVIDER_SLUG,
        },
        { timeoutMs: 90_000 },
      )
      setTestResult(out)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setTestBusy(false)
    }
  }

  const n1x2 = testResult?.normalized_1x2
  const normStatus = n1x2?.normalization_status
  const debugFt = n1x2?.debug_full_time_market ?? n1x2?.raw_market

  return (
    <section className="rounded-2xl border border-emerald-200/80 bg-emerald-50/30 p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-emerald-950">Quote 1X2 — prossimo turno</h2>
      <p className="mt-1 max-w-2xl text-[11px] leading-relaxed text-slate-600">
        Recupero manuale delle quote esito finale (1 / X / 2) per le partite del prossimo turno con
        mapping SportAPI. Solo consultazione — non usate nei pronostici.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void runBatch()}
          disabled={batchBusy}
          className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
        >
          {batchBusy ? 'Recupero in corso…' : 'Recupera 1X2 prossimo turno'}
        </button>
      </div>

      <div className="mt-6 rounded-xl border border-slate-200/80 bg-white/80 p-3">
        <h3 className="text-xs font-semibold text-slate-800">Test singolo evento</h3>
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-slate-600">
            Event ID
            <input
              value={eventId}
              onChange={(e) => setEventId(e.target.value)}
              className="mt-0.5 block w-32 rounded border border-slate-200 px-2 py-1 font-mono text-xs"
            />
          </label>
          <button
            type="button"
            onClick={() => void runTest()}
            disabled={testBusy}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs hover:bg-slate-50 disabled:opacity-50"
          >
            {testBusy ? 'Test…' : 'Testa quote'}
          </button>
        </div>
        {testResult?.working_provider_id != null ? (
          <p className="mt-2 text-xs text-emerald-800">
            provider_id funzionante: <strong>{testResult.working_provider_id}</strong>
            {testResult.candidate_provider_ids?.length ? (
              <span className="text-slate-500">
                {' '}
                (provati: {testResult.candidate_provider_ids.join(', ')})
              </span>
            ) : null}
          </p>
        ) : null}
        {normStatus === 'ok' ? (
          <p className="mt-1 text-xs text-slate-700">
            1X2: <strong>{formatOdd(n1x2?.home_odd)}</strong> /{' '}
            <strong>{formatOdd(n1x2?.draw_odd)}</strong> / <strong>{formatOdd(n1x2?.away_odd)}</strong>
            {n1x2?.market_name_original ? (
              <span className="text-slate-500"> ({n1x2.market_name_original})</span>
            ) : null}
          </p>
        ) : normStatus === 'incomplete' ? (
          <p className="mt-1 text-xs text-amber-700">
            1X2 incompleto — quote parziali: {formatOdd(n1x2?.home_odd)} / {formatOdd(n1x2?.draw_odd)}{' '}
            / {formatOdd(n1x2?.away_odd)}
            {n1x2?.market_name_original ? (
              <span className="text-slate-500"> ({n1x2.market_name_original})</span>
            ) : null}
          </p>
        ) : testResult?.status === 'success' ? (
          <p className="mt-1 text-xs text-amber-700">
            Quote ricevute ma mercato 1X2 non individuato.
            {n1x2?.available_markets?.length
              ? ` Mercati: ${n1x2.available_markets.slice(0, 8).join(', ')}…`
              : null}
          </p>
        ) : null}

        {testResult?.status === 'success' && debugFt != null && normStatus !== 'ok' ? (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setRawFtOpen((o) => !o)}
              className="text-[11px] font-medium text-slate-800 underline"
            >
              {rawFtOpen ? 'Nascondi' : 'Mostra'} Raw mercato Full time
            </button>
            {rawFtOpen ? (
              <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-900 p-2 text-[10px] text-slate-100">
                {JSON.stringify(debugFt, null, 2)}
              </pre>
            ) : null}
          </div>
        ) : null}
      </div>

      {error ? <p className="mt-3 text-xs text-red-600">{error}</p> : null}

      {batchResult ? (
        <div className="mt-4">
          <p className="text-xs text-slate-600">
            Processate {batchResult.processed} / {batchResult.total_fixtures} · senza mapping:{' '}
            {batchResult.skipped_no_mapping}
            {batchResult.working_provider_id != null ? (
              <> · provider_id: {batchResult.working_provider_id}</>
            ) : null}
          </p>
          {batchResult.errors?.length ? (
            <ul className="mt-1 list-inside list-disc text-[10px] text-red-600">
              {batchResult.errors.slice(0, 5).map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          ) : null}
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-[11px]">
              <thead>
                <tr className="border-b border-slate-100 text-slate-500">
                  <th className="py-1 pr-2">Data/Ora</th>
                  <th className="py-1 pr-2">Match</th>
                  <th className="py-1 pr-2 text-center">1</th>
                  <th className="py-1 pr-2 text-center">X</th>
                  <th className="py-1 pr-2 text-center">2</th>
                  <th className="py-1">Stato</th>
                </tr>
              </thead>
              <tbody>
                {(batchResult.rows ?? []).map((r) => (
                  <tr key={r.fixture_id} className="border-b border-slate-50">
                    <td className="py-1.5 pr-2 whitespace-nowrap text-slate-600">
                      {formatKickoff(r.kickoff_at)}
                    </td>
                    <td className="py-1.5 pr-2 font-medium text-slate-900">{r.match_label}</td>
                    <td className="py-1.5 pr-2 text-center font-mono">{formatOdd(r.home_odd)}</td>
                    <td className="py-1.5 pr-2 text-center font-mono">{formatOdd(r.draw_odd)}</td>
                    <td className="py-1.5 pr-2 text-center font-mono">{formatOdd(r.away_odd)}</td>
                    <td className="py-1.5 text-slate-600">
                      {rowStatusLabel(r.status)}
                      {r.error ? (
                        <span className="mt-0.5 block text-[9px] text-red-600">{r.error}</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  )
}
