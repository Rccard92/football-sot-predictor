import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { AuditPageHeader } from '../components/audit/AuditPageHeader'
import { MainDriversPanel } from '../components/audit/MainDriversPanel'
import { MatchAuditHero } from '../components/audit/MatchAuditHero'
import { PredictionAuditSummary } from '../components/audit/PredictionAuditSummary'
import { FrameworkLevelSection } from '../components/audit/FrameworkLevelSection'
import { TechnicalAuditPanel } from '../components/audit/TechnicalAuditPanel'
import type { AuditMode, AuditResponse, FixturesListItem, FixturesListResponse } from '../components/audit/types'

function useQuery(): URLSearchParams {
  const { search } = useLocation()
  return useMemo(() => new URLSearchParams(search), [search])
}

export function MatchVariableAudit() {
  const qs = useQuery()
  const fixtureIdFromQS = Number(qs.get('fixture_id') || '')

  const [fixtures, setFixtures] = useState<FixturesListItem[]>([])
  const [fixtureId, setFixtureId] = useState<number | null>(
    Number.isFinite(fixtureIdFromQS) && fixtureIdFromQS > 0 ? fixtureIdFromQS : null,
  )
  const [mode, setMode] = useState<AuditMode>('pre_match')
  const market = 'shots_on_target' as const

  const [loadingAudit, setLoadingAudit] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<AuditResponse | null>(null)

  useEffect(() => {
    const loadFixtures = async () => {
      setError(null)
      try {
        const res = (await fetch(
          `${import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')}/api/match-analysis/fixtures?scope=upcoming&limit=60`,
        ).then((r) => r.json())) as FixturesListResponse
        setFixtures(res.fixtures ?? [])
        if (fixtureId == null && res.fixtures?.length) {
          setFixtureId(res.fixtures[0].fixture_id)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      }
    }
    void loadFixtures()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const loadAudit = async () => {
      if (!fixtureId) return
      setLoadingAudit(true)
      setError(null)
      try {
        const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')
        const url = `${base}/api/match-analysis/fixture/${fixtureId}/variables?market=${market}&mode=${mode}`
        const res = await fetch(url)
        const parsed = (await res.json()) as unknown
        if (!res.ok) {
          const o = parsed as Record<string, unknown>
          throw new Error((o.message as string) || (o.detail as string) || 'Richiesta non riuscita')
        }
        setData(parsed as AuditResponse)
      } catch (e) {
        setData(null)
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoadingAudit(false)
      }
    }
    void loadAudit()
  }, [fixtureId, mode])

  return (
    <div className="min-h-screen bg-[#F6F7F9] pb-16 pt-2">
      <div className="mx-auto max-w-6xl space-y-6 px-4 sm:px-6">
        <AuditPageHeader
          fixtures={fixtures}
          fixtureId={fixtureId}
          onFixtureChange={(id) => setFixtureId(id)}
          mode={mode}
          onModeChange={(m) => setMode(m)}
          activeModelVersion={data?.active_model_version ?? null}
        />

        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-900">
            {error}
          </div>
        ) : null}

        {loadingAudit ? (
          <div className="space-y-3">
            <div className="h-24 animate-pulse rounded-2xl bg-slate-200/80" />
            <div className="h-48 animate-pulse rounded-2xl bg-slate-200/80" />
          </div>
        ) : data ? (
          <>
            <MatchAuditHero data={data} />
            <PredictionAuditSummary data={data} />
            <MainDriversPanel data={data} />
            <FrameworkLevelSection data={data} />
            <TechnicalAuditPanel data={data} />
          </>
        ) : null}
      </div>
    </div>
  )
}

