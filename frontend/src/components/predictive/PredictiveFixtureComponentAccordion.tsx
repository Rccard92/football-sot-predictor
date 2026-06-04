import { useEffect, useState } from 'react'
import {
  getPredictiveComponentComparisonFixtureDetail,
  type ComponentComparisonFixtureDetail,
} from '../../lib/api'
import { PredictiveComponentComparisonTable } from './PredictiveComponentComparisonTable'

type Props = {
  runId: number
  fixtureId: number
  strategyKey: string
}

export function PredictiveFixtureComponentAccordion({ runId, fixtureId, strategyKey }: Props) {
  const [detail, setDetail] = useState<ComponentComparisonFixtureDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    void getPredictiveComponentComparisonFixtureDetail(runId, fixtureId, strategyKey)
      .then((d) => {
        if (!cancelled) setDetail(d)
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setDetail(null)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [runId, fixtureId, strategyKey])

  if (loading) return <p className="text-xs text-slate-600">Caricamento confronto componenti…</p>
  if (error) return <p className="text-xs text-rose-700">{error}</p>
  if (!detail) return null

  const ms = (detail.match_summary ?? {}) as {
    match?: string
    round_number?: number
    predicted_total_sot?: number
    actual_total_sot?: number
    error?: number
    error_type?: string
  }
  const payload = detail.component_payload ?? {}
  const homeRows = (payload.home?.inputs ?? []).map((inp) => ({
    ...inp,
    match: ms.match,
    round_number: ms.round_number,
    fixture_id: detail.fixture_id,
    strategy_key: detail.strategy_key,
    team: payload.home?.team_name ?? 'Casa',
    team_side: 'home' as const,
    layer: 'team',
  }))
  const awayRows = (payload.away?.inputs ?? []).map((inp) => ({
    ...inp,
    match: ms.match,
    round_number: ms.round_number,
    fixture_id: detail.fixture_id,
    strategy_key: detail.strategy_key,
    team: payload.away?.team_name ?? 'Trasferta',
    team_side: 'away' as const,
    layer: 'team',
  }))
  const matchRows = (payload.match_level?.inputs ?? []).map((inp) => ({
    ...inp,
    match: ms.match,
    round_number: ms.round_number,
    fixture_id: detail.fixture_id,
    strategy_key: detail.strategy_key,
    team: 'Match',
    team_side: 'match' as const,
    layer: 'match',
  }))

  return (
    <div className="mt-3 space-y-3 border-t border-slate-200 pt-3">
      <h4 className="text-xs font-semibold text-violet-900">Confronto componenti Predetto vs Reale</h4>
      <p className="text-xs text-slate-700">
        Totale predetto:{' '}
        {typeof ms.predicted_total_sot === 'number' ? ms.predicted_total_sot.toFixed(1) : '-'} · Reale:{' '}
        {typeof ms.actual_total_sot === 'number' ? ms.actual_total_sot.toFixed(1) : '-'} · Errore:{' '}
        {typeof ms.error === 'number' ? ms.error.toFixed(2) : '-'} (
        {ms.error_type ?? '—'})
      </p>
      <p className="text-[10px] font-medium text-slate-600">Casa</p>
      <PredictiveComponentComparisonTable rows={homeRows} compact />
      <p className="text-[10px] font-medium text-slate-600">Trasferta</p>
      <PredictiveComponentComparisonTable rows={awayRows} compact />
      <p className="text-[10px] font-medium text-slate-600">Match-level</p>
      <PredictiveComponentComparisonTable rows={matchRows} compact />
    </div>
  )
}
