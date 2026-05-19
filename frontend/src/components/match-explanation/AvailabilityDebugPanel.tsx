import { useCallback, useState } from 'react'
import {
  DEFAULT_SEASON,
  getAvailabilityFixtureFlow,
  getAvailabilityLiveFixtureCheck,
} from '../../lib/api'
import type {
  AvailabilityAuditMeta,
  AvailabilityFixtureFlowDebug,
  AvailabilityLiveFixtureCheck,
  FixtureAvailabilityResponse,
} from '../../types/fixtureAvailability'
import { formatFetchError } from '../../utils/formatFetchError'

function jsonPreview(x: unknown): string {
  try {
    return JSON.stringify(x, null, 2)
  } catch {
    return String(x)
  }
}

type Props = {
  fixtureId: number
  season?: number
  auditResponse: FixtureAvailabilityResponse | null
  auditMeta: AvailabilityAuditMeta | null
}

export function AvailabilityDebugPanel({
  fixtureId,
  season = DEFAULT_SEASON,
  auditResponse,
  auditMeta,
}: Props) {
  const [open, setOpen] = useState(false)
  const [flow, setFlow] = useState<AvailabilityFixtureFlowDebug | null>(null)
  const [live, setLive] = useState<AvailabilityLiveFixtureCheck | null>(null)
  const [flowLoading, setFlowLoading] = useState(false)
  const [liveLoading, setLiveLoading] = useState(false)
  const [flowError, setFlowError] = useState<string | null>(null)
  const [liveError, setLiveError] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const [flowLoaded, setFlowLoaded] = useState(false)

  const auditUrl =
    auditMeta?.url ?? `/api/debug/sot/fixture/${fixtureId}/availability`

  const loadFlow = useCallback(async () => {
    setFlowLoading(true)
    setFlowError(null)
    try {
      const data = await getAvailabilityFixtureFlow(season, fixtureId)
      setFlow(data)
      setFlowLoaded(true)
    } catch (e) {
      setFlowError(formatFetchError(e, `GET availability-fixture-flow`))
    } finally {
      setFlowLoading(false)
    }
  }, [fixtureId, season])

  const handleCopy = async (which: 'audit' | 'flow' | 'live' | 'all') => {
    let payload: unknown
    let label: string
    if (which === 'audit') {
      payload = auditResponse
      label = 'audit'
    } else if (which === 'flow') {
      payload = flow
      label = 'fixture-flow'
    } else if (which === 'live') {
      payload = live
      label = 'live-check'
    } else {
      payload = { audit: auditResponse, fixture_flow: flow, live_check: live, audit_meta: auditMeta }
      label = 'completo'
    }
    try {
      await navigator.clipboard.writeText(jsonPreview(payload))
      setCopied(label)
      setTimeout(() => setCopied(null), 2000)
    } catch {
      setCopied('errore')
    }
  }

  const db = flow?.db_checks
  const applicableCount =
    (flow?.applicable_records?.home?.length ?? 0) +
    (flow?.applicable_records?.away?.length ?? 0)
  const excludedCount = flow?.excluded_records?.length ?? 0

  return (
    <details
      className="mt-4 rounded-xl border border-slate-200 bg-slate-50/50"
      open={open}
      onToggle={(e) => {
        const isOpen = (e.target as HTMLDetailsElement).open
        setOpen(isOpen)
        if (isOpen && !flowLoaded && !flowLoading) {
          void loadFlow()
        }
      }}
    >
      <summary className="cursor-pointer select-none px-3 py-2.5 text-xs font-semibold text-slate-800">
        Debug indisponibili
        <span className="ml-2 font-normal text-slate-500">(DB, diagnosi, JSON — chiuso di default)</span>
      </summary>

      <div className="border-t border-slate-200 px-3 py-3 space-y-4">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            disabled={flowLoading}
            onClick={() => void loadFlow()}
          >
            {flowLoading ? 'Caricamento…' : 'Esegui debug indisponibili'}
          </button>
          <button
            type="button"
            className="rounded-lg border border-violet-300 bg-violet-50 px-2.5 py-1 text-[11px] font-medium text-violet-900 hover:bg-violet-100 disabled:opacity-50"
            disabled={liveLoading}
            onClick={async () => {
              setLiveLoading(true)
              setLiveError(null)
              try {
                const data = await getAvailabilityLiveFixtureCheck(season, fixtureId)
                setLive(data)
              } catch (e) {
                setLiveError(formatFetchError(e, 'GET availability-live-fixture-check'))
              } finally {
                setLiveLoading(false)
              }
            }}
          >
            {liveLoading ? 'API live…' : 'Controlla API live per questa fixture'}
          </button>
          <button
            type="button"
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
            onClick={() => void handleCopy('all')}
          >
            {copied === 'completo' ? 'Copiato!' : 'Copia JSON'}
          </button>
        </div>

        {flowError ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-2 py-1.5 text-[11px] text-rose-900">
            {flowError}
          </p>
        ) : null}
        {liveError ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-2 py-1.5 text-[11px] text-rose-900">
            {liveError}
          </p>
        ) : null}

        <div className="rounded-lg border border-slate-200 bg-white p-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Riepilogo</p>
          <ul className="mt-1.5 space-y-0.5 text-[11px] text-slate-700">
            <li>
              fixture_id: <strong>{fixtureId}</strong>
              {flow?.fixture?.api_fixture_id != null ? (
                <>
                  {' '}
                  · api_fixture_id: <strong>{flow.fixture.api_fixture_id}</strong>
                </>
              ) : null}
            </li>
            {flow?.fixture ? (
              <li>
                api team ids: home <strong>{flow.fixture.api_home_team_id}</strong> · away{' '}
                <strong>{flow.fixture.api_away_team_id}</strong>
              </li>
            ) : null}
            {flow ? (
              <li>
                DB applicabili: <strong>{applicableCount}</strong> · esclusi:{' '}
                <strong>{excludedCount}</strong>
                {flow.last_availability_fetched_at ? (
                  <>
                    {' '}
                    · ultimo fetch: <strong>{flow.last_availability_fetched_at}</strong>
                  </>
                ) : null}
              </li>
            ) : null}
          </ul>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Request audit (GET availability partita)
          </p>
          <ul className="mt-1.5 space-y-0.5 text-[11px] text-slate-700">
            <li>
              endpoint: <code className="text-[10px]">{auditUrl}</code>
            </li>
            <li>
              HTTP: <strong>{auditMeta?.httpStatus ?? '—'}</strong>
              {auditMeta?.durationMs != null ? (
                <>
                  {' '}
                  · durata: <strong>{auditMeta.durationMs} ms</strong>
                </>
              ) : null}
            </li>
            {auditMeta?.error ? (
              <li className="text-rose-800">errore: {auditMeta.error}</li>
            ) : null}
            <li>
              records_returned (audit):{' '}
              <strong>{flow?.audit_endpoint?.records_returned ?? '—'}</strong>
            </li>
          </ul>
          <button
            type="button"
            className="mt-2 text-[10px] text-violet-700 underline"
            onClick={() => void handleCopy('audit')}
          >
            Copia JSON audit
          </button>
        </div>

        {flow?.api_football_expected_request ? (
          <div className="rounded-lg border border-slate-200 bg-white p-2.5">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              API attesa (non chiamata automaticamente)
            </p>
            <p className="mt-1 text-[11px] text-slate-700">
              <code>{flow.api_football_expected_request.fixture_request}</code>
              {' · '}
              api_league_id: <strong>{flow.api_football_expected_request.api_league_id}</strong>
            </p>
            <p className="mt-1 text-[10px] text-slate-600">
              {flow.api_football_expected_request.note}
            </p>
          </div>
        ) : null}

        {db ? (
          <div className="rounded-lg border border-slate-200 bg-white p-2.5">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              DB flow
            </p>
            <ul className="mt-1.5 space-y-0.5 text-[11px] text-slate-700">
              <li>
                per api_fixture_id: <strong>{db.player_availability_total_for_fixture_api_id}</strong>
              </li>
              <li>
                home team: <strong>{db.player_availability_total_for_home_team}</strong> · away:{' '}
                <strong>{db.player_availability_total_for_away_team}</strong>
              </li>
              <li>
                fixture-level (campione): <strong>{db.fixture_level_records.length}</strong> · generic non
                applicati: <strong>{db.generic_records_not_applied.length}</strong>
              </li>
            </ul>
            {flow.excluded_records && flow.excluded_records.length > 0 ? (
              <div className="mt-2 overflow-x-auto">
                <table className="min-w-full text-left text-[10px]">
                  <thead className="text-slate-500">
                    <tr>
                      <th className="pr-2 py-0.5">Giocatore</th>
                      <th className="pr-2 py-0.5">Squadra</th>
                      <th className="pr-2 py-0.5">Motivo</th>
                      <th className="pr-2 py-0.5">Scope</th>
                    </tr>
                  </thead>
                  <tbody>
                    {flow.excluded_records.slice(0, 10).map((r, i) => (
                      <tr key={`${r.player_name}-${i}`} className="border-t border-slate-100">
                        <td className="py-0.5 pr-2">{r.player_name}</td>
                        <td className="py-0.5 pr-2">{r.team_name}</td>
                        <td className="py-0.5 pr-2 text-amber-900">{r.reason_excluded}</td>
                        <td className="py-0.5 pr-2">{r.record_scope}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {flow.excluded_records.length > 10 ? (
                  <p className="mt-1 text-[10px] text-slate-500">
                    … altri {flow.excluded_records.length - 10} esclusi
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {flow?.diagnosis && flow.diagnosis.length > 0 ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50/80 p-2.5">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-900">
              Diagnosi
            </p>
            <ul className="mt-1.5 list-disc pl-4 text-[11px] text-amber-950">
              {flow.diagnosis.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {live ? (
          <div className="rounded-lg border border-violet-200 bg-violet-50/50 p-2.5">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-violet-900">
              API live (solo lettura)
            </p>
            <p className="mt-1 text-[11px] text-violet-950">
              {live.request} · risultati: <strong>{live.results ?? 0}</strong>
            </p>
            {live.note ? <p className="mt-0.5 text-[10px] text-violet-800">{live.note}</p> : null}
            <details className="mt-2">
              <summary className="cursor-pointer text-[10px] text-violet-800">JSON live</summary>
              <pre className="mt-1 max-h-48 overflow-auto rounded border border-violet-200 bg-white p-2 text-[9px]">
                {jsonPreview(live)}
              </pre>
            </details>
          </div>
        ) : null}

        <details className="rounded-lg border border-slate-200 bg-white">
          <summary className="cursor-pointer px-2.5 py-2 text-[11px] font-medium text-slate-700">
            JSON espandibili
          </summary>
          <div className="space-y-2 border-t border-slate-100 p-2">
            {flow ? (
              <details>
                <summary className="cursor-pointer text-[10px] text-slate-600">fixture-flow</summary>
                <pre className="mt-1 max-h-40 overflow-auto rounded bg-slate-50 p-2 text-[9px]">
                  {jsonPreview(flow)}
                </pre>
                <button
                  type="button"
                  className="mt-1 text-[10px] text-violet-700 underline"
                  onClick={() => void handleCopy('flow')}
                >
                  Copia fixture-flow
                </button>
              </details>
            ) : null}
            {auditResponse ? (
              <details>
                <summary className="cursor-pointer text-[10px] text-slate-600">audit response</summary>
                <pre className="mt-1 max-h-40 overflow-auto rounded bg-slate-50 p-2 text-[9px]">
                  {jsonPreview(auditResponse)}
                </pre>
              </details>
            ) : null}
          </div>
        </details>
      </div>
    </details>
  )
}

